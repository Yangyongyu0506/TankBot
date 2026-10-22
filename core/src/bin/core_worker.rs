//! Private stdio adapter, never connected to the player worker or browser.
use std::io::{self, Read, Write};
use tankbot_core::session::CoreSession;
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut input = io::stdin().lock();
    let mut output = io::stdout().lock();
    let mut session = CoreSession::default();
    loop {
        let mut length = [0u8; 4];
        match input.read_exact(&mut length) {
            Ok(()) => {}
            Err(e) if e.kind() == io::ErrorKind::UnexpectedEof => return Ok(()),
            Err(e) => return Err(e.into()),
        };
        // Private bootstrap frame limit, not a physical parameter.
        let size = u32::from_be_bytes(length) as usize;
        if size > 1024 * 1024 {
            return Err("Private IPC frame too large".into());
        }
        let mut bytes = vec![0; size];
        input.read_exact(&mut bytes)?;
        let raw = session.exchange(&bytes);
        output.write_all(&(raw.len() as u32).to_be_bytes())?;
        output.write_all(&raw)?;
        output.flush()?;
    }
}
