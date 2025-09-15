import os
import subprocess
import sys

def compile_core(source_dir="./core", output_dir="./build/core"):
    if not os.path.isdir(source_dir):
        print(f"[!] {source_dir} directory not found")
        sys.exit(1)

    for root, _, files in os.walk(source_dir):
        for filename in files:
            if filename.endswith(".py"):
                # full source path
                src = os.path.join(root, filename)

                # preserve folder structure inside build/core
                rel_path = os.path.relpath(root, source_dir)
                dst_dir = os.path.join(output_dir, rel_path)
                os.makedirs(dst_dir, exist_ok=True)

                # compiled file path
                dst = os.path.join(dst_dir, filename[:-3] + ".mpy")

                print(f"[+] Compiling {src} → {dst}")
                result = subprocess.run(
                    [sys.executable, "-m", "mpy_cross", src, "-o", dst],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

                if result.returncode != 0:
                    print(f"[!] Failed: {src}")
                    print(result.stderr)
                else:
                    print(f"[I] Compiled: {dst}")
if __name__ == "__main__":
    subprocess.run([sys.executable, "-m", "mpy_cross", "--version"])

    if len(sys.argv) == 3:
        compile_core(sys.argv[1], sys.argv[2])
    else:
        compile_core()

