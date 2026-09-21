/* Flat C shim over CaDiCaL's C++ API for reasoning/cadical_solver.py.
 *
 * The public C API (ccadical.h) has no `propagate`, and its one-literal-at-a-
 * time `add` makes Python call overhead dominate on small formulas.  This
 * shim exposes the IPASIR-style `propagate` and bulk clause loading used by
 * the drop-in adapter, keeping the comparison with the bundled DPLL solver
 * meaningful.
 */
#include "cadical.hpp"

extern "C" {

void *cadical_shim_init(void) {
  CaDiCaL::Solver *solver = new CaDiCaL::Solver();
  solver->set("quiet", 1);
  return solver;
}

void cadical_shim_release(void *ptr) { delete static_cast<CaDiCaL::Solver *>(ptr); }

void cadical_shim_add(void *ptr, int lit) {
  static_cast<CaDiCaL::Solver *>(ptr)->add(lit);
}

void cadical_shim_add_clauses(void *ptr, const int *literals, int count) {
  CaDiCaL::Solver *solver = static_cast<CaDiCaL::Solver *>(ptr);
  for (int i = 0; i < count; i++) {
    solver->add(literals[i]);
  }
}

int cadical_shim_propagate(void *ptr) {
  return static_cast<CaDiCaL::Solver *>(ptr)->propagate();
}

int cadical_shim_solve(void *ptr) {
  return static_cast<CaDiCaL::Solver *>(ptr)->solve();
}

void cadical_shim_assume(void *ptr, int lit) {
  static_cast<CaDiCaL::Solver *>(ptr)->assume(lit);
}

int cadical_shim_val(void *ptr, int lit) {
  return static_cast<CaDiCaL::Solver *>(ptr)->val(lit);
}

int cadical_shim_fixed(void *ptr, int lit) {
  return static_cast<CaDiCaL::Solver *>(ptr)->fixed(lit);
}

int cadical_shim_failed(void *ptr, int lit) {
  return static_cast<CaDiCaL::Solver *>(ptr)->failed(lit) ? 1 : 0;
}

int cadical_shim_vars(void *ptr) {
  return static_cast<CaDiCaL::Solver *>(ptr)->vars();
}

int cadical_shim_declare_more_variables(void *ptr, int number) {
  return static_cast<CaDiCaL::Solver *>(ptr)->declare_more_variables(number);
}

const char *cadical_shim_signature(void) { return CaDiCaL::Solver::signature(); }

}  // extern "C"
