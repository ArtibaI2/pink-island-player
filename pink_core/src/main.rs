use base64::prelude::*;
use serde::{Deserialize, Serialize};
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;
use windows::Media::Control::{
    GlobalSystemMediaTransportControlsSessionManager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus,
};
use windows::Storage::Streams::{DataReader, IRandomAccessStreamReference};

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct MediaState {
    pub title: String,
    pub artist: String,
    pub album: String,
    pub app_id: String,
    pub is_playing: bool,
    pub position_sec: f64,
    pub duration_sec: f64,
    pub has_session: bool,
    pub thumbnail_b64: Option<String>,
    pub spectrum: Vec<f32>,
}

impl Default for MediaState {
    fn default() -> Self {
        Self {
            title: "Нет воспроизведения".to_string(),
            artist: "Включите трек в Spotify, VK, браузере...".to_string(),
            album: "".to_string(),
            app_id: "".to_string(),
            is_playing: false,
            position_sec: 0.0,
            duration_sec: 180.0,
            has_session: false,
            thumbnail_b64: None,
            spectrum: vec![0.05; 24],
        }
    }
}

fn read_stream_base64(thumb_ref: IRandomAccessStreamReference) -> windows::core::Result<String> {
    let stream = thumb_ref.OpenReadAsync()?.get()?;
    let size = stream.Size()? as usize;
    if size == 0 || size > 10 * 1024 * 1024 {
        return Ok("".to_string());
    }
    let reader = DataReader::CreateDataReader(&stream)?;
    reader.LoadAsync(size as u32)?.get()?;
    let mut bytes = vec![0u8; size];
    reader.ReadBytes(&mut bytes)?;
    Ok(format!("data:image/jpeg;base64,{}", BASE64_STANDARD.encode(&bytes)))
}

fn get_current_media_state(manager: &GlobalSystemMediaTransportControlsSessionManager, cached_state: &MediaState, tick: u64) -> MediaState {
    let session = match manager.GetCurrentSession() {
        Ok(s) => s,
        Err(_) => {
            let mut def = MediaState::default();
            def.spectrum = generate_spectrum(false, tick);
            return def;
        }
    };

    let app_id = session.SourceAppUserModelId().map(|h| h.to_string()).unwrap_or_default();

    let is_playing = if let Ok(info) = session.GetPlaybackInfo() {
        let status = info.PlaybackStatus().unwrap_or(GlobalSystemMediaTransportControlsSessionPlaybackStatus::Closed);
        status == GlobalSystemMediaTransportControlsSessionPlaybackStatus::Playing
    } else {
        false
    };

    let (position_sec, duration_sec) = if let Ok(timeline) = session.GetTimelineProperties() {
        let pos = timeline.Position().map(|p| p.Duration as f64 / 10_000_000.0).unwrap_or(0.0);
        let end = timeline.EndTime().map(|e| e.Duration as f64 / 10_000_000.0).unwrap_or(0.0);
        (pos, end)
    } else {
        (0.0, 180.0)
    };

    let (title, artist, album, mut thumbnail_b64) = if let Ok(prop_op) = session.TryGetMediaPropertiesAsync() {
        if let Ok(props) = prop_op.get() {
            let t = props.Title().map(|h| h.to_string()).unwrap_or_default();
            let a = props.Artist().map(|h| h.to_string()).unwrap_or_default();
            let alb = props.AlbumTitle().map(|h| h.to_string()).unwrap_or_default();
            
            // Only re-extract thumbnail if track changed to avoid high CPU
            let thumb = if t == cached_state.title && cached_state.thumbnail_b64.is_some() {
                cached_state.thumbnail_b64.clone()
            } else if let Ok(thumb_ref) = props.Thumbnail() {
                read_stream_base64(thumb_ref).ok().filter(|s| !s.is_empty())
            } else {
                None
            };
            (t, a, alb, thumb)
        } else {
            ("".to_string(), "".to_string(), "".to_string(), None)
        }
    } else {
        ("".to_string(), "".to_string(), "".to_string(), None)
    };

    if thumbnail_b64.is_none() && title == cached_state.title {
        thumbnail_b64 = cached_state.thumbnail_b64.clone();
    }

    let clean_title = if title.is_empty() { "Аудиопоток Windows".to_string() } else { title };
    let clean_artist = if artist.is_empty() {
        if !app_id.is_empty() {
            app_id.split('\\').last().unwrap_or(&app_id).replace(".exe", "")
        } else {
            "Системный плеер".to_string()
        }
    } else {
        artist
    };

    MediaState {
        title: clean_title,
        artist: clean_artist,
        album,
        app_id,
        is_playing,
        position_sec,
        duration_sec: if duration_sec <= 0.0 { 180.0 } else { duration_sec },
        has_session: true,
        thumbnail_b64,
        spectrum: generate_spectrum(is_playing, tick),
    }
}

fn generate_spectrum(is_playing: bool, tick: u64) -> Vec<f32> {
    let mut bars = Vec::with_capacity(24);
    let t = tick as f32 * 0.15;
    for i in 0..24 {
        if !is_playing {
            bars.push(0.04);
            continue;
        }
        let fi = i as f32;
        let s1 = ((t * 2.1 + fi * 0.45).sin() + 1.0) * 0.25;
        let s2 = ((t * 3.7 - fi * 0.65).cos() + 1.0) * 0.20;
        let s3 = ((t * 1.1 + fi * 0.2).sin() + 1.0) * 0.15;
        // Peak pulse every few beats
        let beat = ((t * 4.0).sin().powi(4)) * 0.35 * (1.0 - (fi / 24.0));
        let val = (s1 + s2 + s3 + beat).clamp(0.08, 1.0);
        bars.push(val);
    }
    bars
}

pub fn execute_command(manager: &GlobalSystemMediaTransportControlsSessionManager, cmd: &str) {
    if let Ok(session) = manager.GetCurrentSession() {
        match cmd {
            "play" => { let _ = session.TryPlayAsync(); }
            "pause" => { let _ = session.TryPauseAsync(); }
            "toggle" => { let _ = session.TryTogglePlayPauseAsync(); }
            "next" => { let _ = session.TrySkipNextAsync(); }
            "prev" => { let _ = session.TrySkipPreviousAsync(); }
            s if s.starts_with("seek:") => {
                if let Ok(sec) = s[5..].parse::<f64>() {
                    let ticks = (sec * 10_000_000.0) as i64;
                    let _ = session.TryChangePlaybackPositionAsync(ticks);
                }
            }
            _ => {}
        }
    }
}

fn handle_client(mut stream: TcpStream, state_arc: Arc<Mutex<MediaState>>, manager: Arc<GlobalSystemMediaTransportControlsSessionManager>) {
    let mut buffer = [0u8; 2048];
    if let Ok(n) = stream.read(&mut buffer) {
        let req = String::from_utf8_lossy(&buffer[..n]);
        let first_line = req.lines().next().unwrap_or("");
        
        let (status, response_body) = if first_line.starts_with("GET /api/state") {
            let state = state_arc.lock().unwrap();
            ("200 OK", serde_json::to_string(&*state).unwrap_or_else(|_| "{}".to_string()))
        } else if first_line.starts_with("POST /api/command") || first_line.starts_with("GET /api/command") {
            // Extract command from URL or query string
            let cmd = if let Some(idx) = first_line.find("cmd=") {
                let rest = &first_line[idx + 4..];
                rest.split_whitespace().next().unwrap_or("").split('&').next().unwrap_or("")
            } else {
                ""
            };
            execute_command(&manager, cmd);
            ("200 OK", r#"{"status":"ok"}"#.to_string())
        } else if first_line.starts_with("OPTIONS") {
            ("200 OK", "".to_string())
        } else {
            ("404 Not Found", r#"{"error":"not found"}"#.to_string())
        };
        let content_type = "application/json";

        let resp = format!(
            "HTTP/1.1 {}\r\nContent-Type: {}\r\nAccess-Control-Allow-Origin: *\r\nAccess-Control-Allow-Methods: GET, POST, OPTIONS\r\nAccess-Control-Allow-Headers: Content-Type\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
            status,
            content_type,
            response_body.len(),
            response_body
        );
        let _ = stream.write_all(resp.as_bytes());
        let _ = stream.flush();
    }
}

fn main() -> windows::core::Result<()> {
    let manager = Arc::new(GlobalSystemMediaTransportControlsSessionManager::RequestAsync()?.get()?);
    let state = Arc::new(Mutex::new(MediaState::default()));

    // Polling thread for media state
    let state_clone = Arc::clone(&state);
    let manager_clone = Arc::clone(&manager);
    thread::spawn(move || {
        let mut tick: u64 = 0;
        let mut cached = MediaState::default();
        loop {
            tick = tick.wrapping_add(1);
            let new_state = get_current_media_state(&manager_clone, &cached, tick);
            cached = new_state.clone();
            {
                let mut lock = state_clone.lock().unwrap();
                *lock = new_state;
            }
            thread::sleep(Duration::from_millis(100));
        }
    });

    let listener = TcpListener::bind("127.0.0.1:48123").expect("Failed to bind TCP port 48123");
    println!("PINK_CORE_READY: http://127.0.0.1:48123");

    for stream in listener.incoming() {
        if let Ok(stream) = stream {
            let state_ref = Arc::clone(&state);
            let manager_ref = Arc::clone(&manager);
            thread::spawn(move || {
                handle_client(stream, state_ref, manager_ref);
            });
        }
    }

    Ok(())
}
