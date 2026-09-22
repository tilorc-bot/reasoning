"""Self-registering refine handlers, one module per registry key.

Every module in this package (except ones whose name starts with ``_``) is
imported automatically by :mod:`reasoning.refine`.  A module registers its
handler by assigning to ``handlers_dict``; it must not register a key owned
by another module.
"""
