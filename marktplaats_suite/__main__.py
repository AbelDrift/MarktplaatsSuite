"""python -m marktplaats_suite [module]  (zonder argument: startscherm)"""
import importlib
import sys

NAMEN = ("productmanager", "fotomanager", "scanner", "automater")

if len(sys.argv) > 1 and sys.argv[1] in NAMEN:
    importlib.import_module(f"marktplaats_suite.{sys.argv[1]}").main()
else:
    from marktplaats_suite.launcher import main
    main()
