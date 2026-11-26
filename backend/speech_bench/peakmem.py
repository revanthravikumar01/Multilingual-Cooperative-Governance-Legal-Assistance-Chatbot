import atexit, runpy, sys, torch
atexit.register(lambda: print(f"peak GPU memory: {torch.cuda.max_memory_allocated() / 1e9:.2f} GB", flush=True))
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name="__main__")
