//! Reasoning core: clause storage and a CaDiCaL session behind a coarse C ABI.
//!
//! Python owns no per-literal or per-variable state: clauses cross this
//! boundary once per formula (flat, zero-terminated), and the model crosses
//! once per solve.  CaDiCaL is reached through the vendored C++ shim, which
//! provides the IPASIR-style root `propagate`/`fixed` pair the engine needs.

use std::os::raw::{c_char, c_int, c_void};
use std::ptr;
use std::slice;

extern "C" {
    fn cadical_shim_init() -> *mut c_void;
    fn cadical_shim_release(solver: *mut c_void);
    fn cadical_shim_add(solver: *mut c_void, lit: c_int);
    fn cadical_shim_add_clauses(solver: *mut c_void, literals: *const c_int, count: c_int);
    fn cadical_shim_propagate(solver: *mut c_void) -> c_int;
    fn cadical_shim_solve(solver: *mut c_void) -> c_int;
    fn cadical_shim_assume(solver: *mut c_void, lit: c_int);
    fn cadical_shim_val(solver: *mut c_void, lit: c_int) -> c_int;
    fn cadical_shim_fixed(solver: *mut c_void, lit: c_int) -> c_int;
    fn cadical_shim_declare_more_variables(solver: *mut c_void, number: c_int) -> c_int;
    fn cadical_shim_signature() -> *const c_char;
}

/// A CaDiCaL session plus the largest variable index declared so far.
struct Core {
    solver: *mut c_void,
    max_var: c_int,
}

impl Core {
    fn ensure_variable(&mut self, var: c_int) {
        if var > self.max_var {
            unsafe {
                cadical_shim_declare_more_variables(self.solver, var - self.max_var);
            }
            self.max_var = var;
        }
    }
}

/// Return the CaDiCaL version string compiled into this library.
#[no_mangle]
pub extern "C" fn rcore_signature() -> *const c_char {
    unsafe { cadical_shim_signature() }
}

/// Create a session with variables ``1..=max_var`` declared.
#[no_mangle]
pub extern "C" fn rcore_new(max_var: c_int) -> *mut c_void {
    let solver = unsafe { cadical_shim_init() };
    if solver.is_null() {
        return ptr::null_mut();
    }
    let max_var = if max_var < 0 { 0 } else { max_var };
    if max_var > 0 {
        unsafe {
            cadical_shim_declare_more_variables(solver, max_var);
        }
    }
    Box::into_raw(Box::new(Core { solver, max_var })) as *mut c_void
}

/// Release a session created by [`rcore_new`].
#[no_mangle]
pub extern "C" fn rcore_free(solver: *mut c_void) {
    if solver.is_null() {
        return;
    }
    let core = unsafe { Box::from_raw(solver as *mut Core) };
    unsafe {
        cadical_shim_release(core.solver);
    }
    drop(core);
}

/// Add zero-terminated clauses from one flat buffer.
///
/// Literals are deduplicated and tautological clauses are dropped here, in
/// bulk, so neither Python nor CaDiCaL sees them.  Returns 1 on success and 0
/// for a null or malformed buffer.
#[no_mangle]
pub extern "C" fn rcore_add_clauses(
    solver: *mut c_void,
    flat: *const c_int,
    len: usize,
) -> c_int {
    if solver.is_null() {
        return 0;
    }
    if len == 0 {
        return 1;
    }
    if flat.is_null() || len > c_int::MAX as usize {
        return 0;
    }
    let core = unsafe { &mut *(solver as *mut Core) };
    let input = unsafe { slice::from_raw_parts(flat, len) };

    let mut normalized: Vec<c_int> = Vec::with_capacity(len);
    let mut clause: Vec<c_int> = Vec::new();
    let mut tautological = false;
    let mut open = false;
    for &lit in input {
        if lit == 0 {
            if !tautological {
                normalized.extend_from_slice(&clause);
                normalized.push(0);
            }
            clause.clear();
            tautological = false;
            open = false;
            continue;
        }
        if lit == c_int::MIN {
            return 0;
        }
        open = true;
        core.ensure_variable(lit.abs());
        if clause.contains(&-lit) {
            tautological = true;
        } else if !clause.contains(&lit) {
            clause.push(lit);
        }
    }
    if open && !tautological {
        normalized.extend_from_slice(&clause);
        normalized.push(0);
    }
    if normalized.is_empty() {
        return 1;
    }
    unsafe {
        cadical_shim_add_clauses(core.solver, normalized.as_ptr(), normalized.len() as c_int);
    }
    1
}

/// Add one literal to the clause being built; zero terminates the clause.
#[no_mangle]
pub extern "C" fn rcore_add(solver: *mut c_void, lit: c_int) {
    if solver.is_null() {
        return;
    }
    unsafe {
        cadical_shim_add((*(solver as *mut Core)).solver, lit);
    }
}

/// Propagate root-level units without deciding; returns 0, 10, or 20.
#[no_mangle]
pub extern "C" fn rcore_propagate(solver: *mut c_void) -> c_int {
    if solver.is_null() {
        return 0;
    }
    unsafe { cadical_shim_propagate((*(solver as *mut Core)).solver) }
}

/// Return 1 if *lit* is root-fixed, -1 if its negation is, and 0 otherwise.
#[no_mangle]
pub extern "C" fn rcore_fixed(solver: *mut c_void, lit: c_int) -> c_int {
    if solver.is_null() || lit == 0 {
        return 0;
    }
    let value = unsafe { cadical_shim_fixed((*(solver as *mut Core)).solver, lit) };
    if value > 0 {
        1
    } else if value < 0 {
        -1
    } else {
        0
    }
}

/// Assume *lit* for the next solve.
#[no_mangle]
pub extern "C" fn rcore_assume(solver: *mut c_void, lit: c_int) {
    if solver.is_null() || lit == 0 {
        return;
    }
    unsafe {
        cadical_shim_assume((*(solver as *mut Core)).solver, lit);
    }
}

/// Solve under the assumptions collected since the last solve; returns 10/20.
#[no_mangle]
pub extern "C" fn rcore_solve(solver: *mut c_void) -> c_int {
    if solver.is_null() {
        return 0;
    }
    unsafe { cadical_shim_solve((*(solver as *mut Core)).solver) }
}

/// Return the signed model value of *lit* (``lit``, ``-lit``, or 0).
#[no_mangle]
pub extern "C" fn rcore_val(solver: *mut c_void, lit: c_int) -> c_int {
    if solver.is_null() || lit == 0 {
        return 0;
    }
    unsafe { cadical_shim_val((*(solver as *mut Core)).solver, lit) }
}

/// Fill ``out[var - 1]`` with the signed model value of variables ``1..=len``.
///
/// Returns the number of variables written, which lets the Python wrapper read
/// the whole model in one crossing.
#[no_mangle]
pub extern "C" fn rcore_model(solver: *mut c_void, out: *mut c_int, len: usize) -> c_int {
    if solver.is_null() || out.is_null() {
        return 0;
    }
    let core = unsafe { &mut *(solver as *mut Core) };
    let mut written: c_int = 0;
    for var in 1..=len {
        if var > c_int::MAX as usize {
            break;
        }
        let value = unsafe { cadical_shim_val(core.solver, var as c_int) };
        unsafe {
            *out.add(var - 1) = value;
        }
        written += 1;
    }
    written
}
