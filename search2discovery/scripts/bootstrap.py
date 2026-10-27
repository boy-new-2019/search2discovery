#!/usr/bin/env python3
"""Install sibling personal Skills and bundled profiles into a research workspace."""
import importlib.util,pathlib,sys
PUBLIC=pathlib.Path(__file__).resolve().parents[1]
def main(argv=None):
    path=PUBLIC/'resources/install_v6.py'
    spec=importlib.util.spec_from_file_location('s2d_bootstrap_installer',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.ROOT=PUBLIC.parent
    return module.main(argv)
if __name__=='__main__':raise SystemExit(main())
