use std::sync::Mutex;

use tauri::{Manager, RunEvent};
#[cfg(not(debug_assertions))]
use tauri_plugin_shell::{process::CommandEvent, ShellExt};

struct BackendSidecar(Mutex<Option<tauri_plugin_shell::process::CommandChild>>);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|_app| {
            #[cfg(not(debug_assertions))]
            start_backend_sidecar(_app)?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building Shot Reader")
        .run(|app_handle, event| {
            if let RunEvent::Exit = event {
                if let Some(state) = app_handle.try_state::<BackendSidecar>() {
                    if let Some(child) = state.0.lock().ok().and_then(|mut guard| guard.take()) {
                        let _ = child.kill();
                    }
                }
            }
        });
}

#[cfg(not(debug_assertions))]
fn start_backend_sidecar(app: &mut tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let data_dir = app.path().app_data_dir()?;
    std::fs::create_dir_all(&data_dir)?;

    let sidecar = app
        .shell()
        .sidecar("backend-sidecar")?
        .env("SHOT_READER_DATA_DIR", data_dir.as_os_str())
        .env("VIDEO_AGENT_HOST", "127.0.0.1")
        .env("VIDEO_AGENT_PORT", "8765")
        .env("VIDEO_AGENT_LOG_LEVEL", "warning");

    let (mut rx, child) = sidecar.spawn()?;
    app.manage(BackendSidecar(Mutex::new(Some(child))));

    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    println!("[backend] {}", String::from_utf8_lossy(&line));
                }
                CommandEvent::Stderr(line) => {
                    eprintln!("[backend] {}", String::from_utf8_lossy(&line));
                }
                CommandEvent::Error(error) => {
                    eprintln!("[backend] {error}");
                }
                CommandEvent::Terminated(payload) => {
                    eprintln!("[backend] exited with code {:?}", payload.code);
                }
                _ => {}
            }
        }
    });
    Ok(())
}
