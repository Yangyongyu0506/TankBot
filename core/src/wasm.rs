//! Single-threaded, caller-owned Worker ABI. Buffers belong to Rust and never cross Workers.
use crate::session::CoreSession;
use std::cell::RefCell;

#[derive(Default)]
struct Bridge {
    session: CoreSession,
    input: Vec<u8>,
    output: Vec<u8>,
}
thread_local! { static BRIDGE: RefCell<Bridge> = RefCell::new(Bridge::default()); }

/// Allocate/resize the input slot; invalidates previous buffer pointers. Maximum private DTO: 1 MiB.
#[unsafe(no_mangle)]
pub extern "C" fn tankbot_input(size: u32) -> *mut u8 {
    if size > 1024 * 1024 {
        return std::ptr::null_mut();
    }
    BRIDGE.with_borrow_mut(|b| {
        b.input.resize(size as usize, 0);
        b.input.as_mut_ptr()
    })
}

/// Consume the whole input slot and return output byte count. No reentrant/concurrent calls.
#[unsafe(no_mangle)]
pub extern "C" fn tankbot_exchange() -> u32 {
    BRIDGE.with_borrow_mut(|b| {
        b.output = b.session.exchange(&b.input);
        b.output.len() as u32
    })
}

/// Read-only output slot, valid until the next call. JS must reacquire memory.buffer after growth.
#[unsafe(no_mangle)]
pub extern "C" fn tankbot_output() -> *const u8 {
    BRIDGE.with_borrow(|b| b.output.as_ptr())
}
