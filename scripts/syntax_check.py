#!/usr/bin/env python3
import os
import sys
import py_compile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse

def check_file(file_path):
    try:
        py_compile.compile(file_path, doraise=True)
        return True, None
    except py_compile.PyCompileError as e:
        return False, str(e)
    except Exception as e:
        return False, f"Unexpected error: {e}"

def find_python_files(root_dir, exclude_dirs=None):
    if exclude_dirs is None:
        exclude_dirs = {'.git', '__pycache__', '.venv', 'venv', 'node_modules', '.pytest_cache'}
    python_files = []
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))
    return python_files

def main():
    parser = argparse.ArgumentParser(description='Syntax check Python files')
    parser.add_argument('--dir', default='.', help='Directory to check (default: current)')
    parser.add_argument('--exclude', nargs='*', default=[], help='Additional directories to exclude')
    parser.add_argument('--threads', type=int, default=8, help='Number of parallel threads')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    args = parser.parse_args()

    root_dir = args.dir
    exclude_set = {'.git', '__pycache__', '.venv', 'venv', 'node_modules', '.pytest_cache', 'tests'}
    exclude_set.update(args.exclude)

    print(f"🔍 Searching for Python files in: {root_dir}")
    python_files = find_python_files(root_dir, exclude_set)
    print(f"📁 Found {len(python_files)} Python files")

    errors = []
    success_count = 0

    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        futures = {executor.submit(check_file, f): f for f in python_files}
        for i, future in enumerate(as_completed(futures), 1):
            file_path = futures[future]
            try:
                is_valid, error_msg = future.result()
                if is_valid:
                    success_count += 1
                    if args.verbose:
                        print(f"✅ {file_path}")
                else:
                    errors.append((file_path, error_msg))
                    print(f"❌ {file_path}")
            except Exception as e:
                errors.append((file_path, str(e)))
                print(f"❌ {file_path}: {e}")

            if i % 50 == 0:
                print(f"📊 Progress: {i}/{len(python_files)}")

    print(f"\n{'='*50}")
    print(f"📊 语法检查完成!")
    print(f"✅ 通过: {success_count}/{len(python_files)}")
    print(f"❌ 失败: {len(errors)}/{len(python_files)}")

    if errors:
        print(f"\n❌ 错误详情:")
        for file_path, error_msg in errors[:20]:
            print(f"\n  文件: {file_path}")
            print(f"  错误: {error_msg[:200]}...")
        if len(errors) > 20:
            print(f"\n  ... 还有 {len(errors) - 20} 个错误")
        return 1
    else:
        print(f"\n✅ 所有文件语法正确!")
        return 0

if __name__ == '__main__':
    sys.exit(main())