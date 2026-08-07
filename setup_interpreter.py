"""Interprets setup instructions from .setup files."""
import os
import sys
import subprocess
import shutil
import time
import re
import threading
from pathlib import Path
from tqdm import tqdm

def find_python_versions():
    """Find all available Python versions on the system."""
    versions = {}

    possible_names = [
        "python", "python3",
        "python3.8", "python3.9", "python3.10", "python3.11", "python3.12", "python3.13", "python3.14",
    ]

    for minor in range(8, 14):
        possible_names.append(f"python3.{minor}")

    for name in possible_names:
        path = shutil.which(name)
        if path:
            try:
                result = subprocess.run(
                    [path, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    version_str = result.stdout.strip().split()[1]
                    versions[version_str] = path
            except (subprocess.TimeoutExpired, Exception):
                continue

    return versions


def run_with_smooth_progress(cmd, description="Running", total_steps=50):
    """Run a command with a smooth animated progress bar."""
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )

    # Create progress bar
    with tqdm(total=100, desc=description, bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt}") as pbar:
        output_lines = []
        current_progress = 0

        # Keywords that indicate progress
        progress_keywords = {
            'Collecting': 2,
            'Downloading': 3,
            'Installing collected': 5,
            'Running setup': 2,
            'Building wheel': 3,
            'Requirement already': 5,
            'Successfully installed': 100,
        }

        # Thread for reading output
        def read_output():
            for line in iter(process.stdout.readline, ''):
                if line:
                    output_lines.append(line)
                    # Check for progress keywords
                    for keyword, increment in progress_keywords.items():
                        if keyword in line:
                            nonlocal current_progress
                            # Don't go over 95% until we see success
                            if current_progress < 95:
                                current_progress = min(current_progress + increment, 95)
                                pbar.update(increment)
                            break

        # Start output reader thread
        reader_thread = threading.Thread(target=read_output)
        reader_thread.daemon = True
        reader_thread.start()

        # Animate progress while waiting
        while process.poll() is None:
            # Slowly creep forward if no progress detected
            if current_progress < 90:
                current_progress += 1
                pbar.update(1)
            time.sleep(0.1)

        # Wait for thread to finish
        reader_thread.join(timeout=1)

        # Check if completed successfully
        if process.returncode == 0:
            # Jump to 100% on success
            if current_progress < 100:
                pbar.update(100 - current_progress)
        else:
            # Show error state
            pbar.colour = 'red'
            pbar.update(100 - current_progress)

        return process.returncode, ''.join(output_lines)


def run_with_animated_spinner(cmd, description="Running"):
    """Run a command with an animated spinner for quick operations."""
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )

    # Simple spinner
    spinner = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    idx = 0

    with tqdm(total=100, desc=description, bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt}") as pbar:
        # Animate while process runs
        while process.poll() is None:
            pbar.set_description(f"{description} {spinner[idx % len(spinner)]}")
            idx += 1
            time.sleep(0.1)
            # Slowly increment
            if pbar.n < 90:
                pbar.update(1)

        # Complete
        if process.returncode == 0:
            pbar.update(100 - pbar.n)

        return process.returncode, process.communicate()[0]


def edit_file(project_dir, file_path, operation, content=None, pattern=None, replacement=None):
    """Edit a file in the project directory with various operations.

    Args:
        project_dir: Base project directory
        file_path: Path to file (relative to project_dir)
        operation: Type of operation - 'append', 'prepend', 'replace', 'insert_after', 'remove'
        content: Content to append/prepend/insert
        pattern: Pattern to search for (for replace/remove/insert_after)
        replacement: Replacement text (for replace operation)
    """
    full_path = Path(project_dir) / file_path

    if not full_path.exists():
        print(f"[ERROR] File not found: {file_path}")
        return False

    # Read existing content
    with open(full_path, 'r') as f:
        lines = f.readlines()

    modified = False
    new_lines = []

    if operation == 'append':
        # Append content at the end
        if content:
            # Add newline if not present
            if lines and not lines[-1].endswith('\n'):
                lines[-1] += '\n'
            lines.append(content + '\n')
            modified = True

    elif operation == 'prepend':
        # Insert content at the beginning
        if content:
            lines.insert(0, content + '\n')
            modified = True

    elif operation == 'replace':
        # Replace all occurrences of pattern with replacement
        if pattern and replacement is not None:
            for line in lines:
                if pattern in line:
                    new_lines.append(line.replace(pattern, replacement))
                    modified = True
                else:
                    new_lines.append(line)
            if modified:
                lines = new_lines

    elif operation == 'insert_after':
        # Insert content after the first line containing pattern
        if pattern and content:
            inserted = False
            for line in lines:
                new_lines.append(line)
                if pattern in line and not inserted:
                    new_lines.append(content + '\n')
                    inserted = True
                    modified = True
            if modified:
                lines = new_lines

    elif operation == 'remove':
        # Remove all lines containing pattern
        if pattern:
            for line in lines:
                if pattern not in line:
                    new_lines.append(line)
                else:
                    modified = True
            if modified:
                lines = new_lines

    elif operation == 'replace_line':
        # Replace entire line containing pattern
        if pattern and replacement is not None:
            for line in lines:
                if pattern in line:
                    new_lines.append(replacement + '\n')
                    modified = True
                else:
                    new_lines.append(line)
            if modified:
                lines = new_lines

    else:
        print(f"[ERROR] Unknown operation: {operation}")
        return False

    if modified:
        # Write back the modified content
        with open(full_path, 'w') as f:
            f.writelines(lines)
        print(f"[EDIT] Updated file: {file_path} (operation: {operation})")
        return True
    else:
        print(f"[INFO] No changes made to: {file_path}")
        return False


def install_from_requirements(project_dir, dev=False):
    """Install packages from requirements.txt file.

    Args:
        project_dir: Base project directory
        dev: If True, install development dependencies from requirements-dev.txt
    """
    venv_dir = Path(project_dir) / ".venv"

    if not venv_dir.exists():
        print("[ERROR] No virtual environment found. Create one first with 'makevenv'")
        return False

    # Get python executable
    if sys.platform == "win32":
        python_exe = venv_dir / "Scripts" / "python.exe"
    else:
        python_exe = venv_dir / "bin" / "python"

    if not python_exe.exists():
        print(f"[ERROR] Python executable not found at {python_exe}")
        return False

    # Determine which requirements file to use
    req_file = "requirements-dev.txt" if dev else "requirements.txt"
    req_path = Path(project_dir) / req_file

    if not req_path.exists():
        print(f"[WARNING] {req_file} not found at {req_path}")
        return False

    print(f"[INFO] Installing from {req_file}...")

    # Use python -m pip install -r requirements.txt
    try:
        returncode, output = run_with_smooth_progress(
            [str(python_exe), "-m", "pip", "install", "-r", str(req_path)],
            description=f"Installing from {req_file}",
            total_steps=50
        )

        if returncode == 0:
            print(f"[OK] Successfully installed packages from {req_file}")
            return True
        else:
            print(f"[ERROR] Failed to install packages from {req_file}")
            if output:
                error_lines = [line for line in output.split('\n') if 'error' in line.lower()]
                if error_lines:
                    for error in error_lines[:3]:
                        print(f"  {error.strip()}")
            return False

    except Exception as e:
        print(f"[ERROR] Exception while installing from {req_file}: {e}")
        return False

def make_venv(project_dir, python_version=None):
    """Create a virtual environment with animated progress."""
    venv_dir = Path(project_dir) / ".venv"

    if venv_dir.exists():
        print(f"[OK] Virtual environment already exists at {venv_dir}")
        return venv_dir

    python_path = sys.executable

    if python_version:
        versions = find_python_versions()

        if not versions:
            print("[ERROR] No Python installations found!")
            return None

        matching = {v: p for v, p in versions.items() if v.startswith(python_version)}

        if not matching:
            print(f"[ERROR] Python {python_version} not found. Available versions:")
            for v in sorted(versions.keys()):
                print(f"  - Python {v} ({versions[v]})")
            return None

        best_version = sorted(matching.keys())[-1]
        python_path = matching[best_version]
        print(f"[INFO] Using Python {best_version} ({python_path})")
    else:
        print(f"[INFO] Using current Python ({python_path})")

    print("[INFO] Creating virtual environment...")

    # Create venv with spinner (it's usually fast)
    returncode, output = run_with_animated_spinner(
        [python_path, "-m", "venv", str(venv_dir)],
        description="Creating venv"
    )

    if returncode != 0:
        print(f"[ERROR] Error creating virtual environment")
        return None

    print(f"[OK] Virtual environment created at {venv_dir}")

    # Get python executable
    if sys.platform == "win32":
        python_exe = venv_dir / "Scripts" / "python.exe"
    else:
        python_exe = venv_dir / "bin" / "python"

    # Upgrade pip with smooth progress
    print("[INFO] Upgrading pip...")
    returncode, output = run_with_smooth_progress(
        [str(python_exe), "-m", "pip", "install", "--upgrade", "pip"],
        description="Upgrading pip",
        total_steps=50
    )

    if returncode == 0:
        print("[OK] Pip upgraded successfully")
    else:
        print("[WARNING] Pip upgrade had issues")

    return venv_dir


def pip_install(project_dir, packages, dev=False):
    """Install packages with smooth progress bars."""
    venv_dir = Path(project_dir) / ".venv"

    if not venv_dir.exists():
        print("[ERROR] No virtual environment found. Create one first with 'makevenv'")
        return False

    # Get python executable
    if sys.platform == "win32":
        python_exe = venv_dir / "Scripts" / "python.exe"
    else:
        python_exe = venv_dir / "bin" / "python"

    if not python_exe.exists():
        print(f"[ERROR] Python executable not found at {python_exe}")
        return False

    # Install each package with smooth progress
    for package in packages:
        print(f"\n[INFO] Installing {package}...")

        # Run pip install with smooth progress
        returncode, output = run_with_smooth_progress(
            [str(python_exe), "-m", "pip", "install", package],
            description=f"Installing {package}",
            total_steps=50
        )

        if returncode == 0:
            # Extract package version from output
            version_match = re.search(r'Successfully installed.*?([\w-]+-\S+)', output)
            if version_match:
                print(f"[OK] Installed {version_match.group(1)}")
            else:
                print(f"[OK] Installed {package}")
        else:
            print(f"[ERROR] Failed to install {package}")
            # Show error details
            if output:
                error_lines = [line for line in output.split('\n') if 'error' in line.lower()]
                if error_lines:
                    for error in error_lines[:3]:
                        print(f"  {error.strip()}")
            return False

    return True


def make_folder(project_dir, folder_path):
    """Create a folder in the project directory."""
    full_path = Path(project_dir) / folder_path
    full_path.mkdir(parents=True, exist_ok=True)
    print(f"[FOLDER] Created folder: {folder_path}")


def make_file(project_dir, file_path, content=""):
    """Create a file in the project directory."""
    full_path = Path(project_dir) / file_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content)
    print(f"[FILE] Created file: {file_path}")


def ask_input(prompt, default=None, var_name=None):
    """Ask for user input."""
    if default:
        user_input = input(f"[INPUT] {prompt} [{default}]: ").strip()
    else:
        user_input = input(f"[INPUT] {prompt}: ").strip()

    if not user_input and default:
        user_input = default

    if var_name:
        return var_name, user_input

    return None, user_input


def run_setup_commands(project_dir, commands, context=None):
    """Run setup commands from a .setup file."""
    if context is None:
        context = {}

    variables = {}

    for cmd in commands:
        cmd = cmd.strip()
        if not cmd or cmd.startswith("#"):
            continue

        # Replace variables in command
        for var_name, var_value in {**context, **variables}.items():
            cmd = cmd.replace(f"${{{var_name}}}", str(var_value))

        print(f"\n[RUN] Running: {cmd}")

        parts = cmd.split()
        action = parts[0].lower()

        if action == "makevenv":
            version = parts[1] if len(parts) > 1 else None
            make_venv(project_dir, version)

        elif action == "pkginstall":
            packages = parts[1:]
            pip_install(project_dir, packages)

        elif action == "pkginstalldev":
            packages = parts[1:]
            pip_install(project_dir, packages, dev=True)

        elif action == "makefolder":
            for folder in parts[1:]:
                make_folder(project_dir, folder)

        elif action == "makefile":
            if len(parts) >= 2:
                file_path = parts[1]
                content = " ".join(parts[2:]) if len(parts) > 2 else ""
                make_file(project_dir, file_path, content)

        elif action == "initgit":
            with tqdm(total=100, desc="Initializing git", bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt}") as pbar:
                # Animate while git initializes
                for i in range(10):
                    time.sleep(0.1)
                    pbar.update(10)
                result = subprocess.run(["git", "init", str(project_dir)], capture_output=True)
                pbar.update(100 - pbar.n)

            if result.returncode == 0:
                print("[OK] Initialized git repository")
            else:
                print("[WARNING] Git initialization failed")

        elif action == "ask":
            # Already handled in collect_variables, just skip here
            pass

        elif action == "echo":
            print(" ".join(parts[1:]))

        elif action == "installreq":
            # Install from requirements.txt
            install_from_requirements(project_dir, dev=False)

        elif action == "installreqdev":
            # Install from requirements-dev.txt (development dependencies)
            install_from_requirements(project_dir, dev=True)

        elif action == "editfile":
            # Parse editfile command
            # Format: editfile <file_path> <operation> [args...]
            if len(parts) >= 3:
                file_path = parts[1]
                operation = parts[2].lower()

                # Parse additional arguments based on operation
                content = None
                pattern = None
                replacement = None

                # Parse remaining args
                remaining = " ".join(parts[3:]) if len(parts) > 3 else ""

                # Extract quoted content
                if remaining:
                    # Check for content in quotes
                    if '"' in remaining or "'" in remaining:
                        # Try to extract quoted content
                        quote_char = '"' if '"' in remaining else "'"
                        start_quote = remaining.find(quote_char)
                        if start_quote != -1:
                            end_quote = remaining.find(quote_char, start_quote + 1)
                            if end_quote != -1:
                                content = remaining[start_quote + 1:end_quote]
                                remaining = remaining[end_quote + 1:].strip()

                    # Parse remaining as pattern/replacement
                    if remaining and operation in ['replace', 'replace_line', 'insert_after', 'remove']:
                        # Try to split by whitespace, but respect quotes
                        parts_remaining = remaining.split()
                        if len(parts_remaining) >= 1:
                            pattern = parts_remaining[0].strip()
                            if len(parts_remaining) >= 2:
                                # Check if replacement is quoted
                                if parts_remaining[1].startswith('"') or parts_remaining[1].startswith("'"):
                                    quote_char = parts_remaining[1][0]
                                    # Join remaining parts until closing quote
                                    replacement_parts = []
                                    found_end = False
                                    for i, part in enumerate(parts_remaining[1:]):
                                        if part.endswith(quote_char):
                                            replacement_parts.append(part[:-1])
                                            found_end = True
                                            break
                                        else:
                                            replacement_parts.append(part)
                                    if found_end:
                                        replacement = " ".join(replacement_parts)
                                    else:
                                        # Use all remaining as replacement
                                        replacement = " ".join(parts_remaining[1:])
                                else:
                                    replacement = " ".join(parts_remaining[1:])

                # Call edit_file with parsed arguments
                edit_file(
                    project_dir,
                    file_path,
                    operation,
                    content=content,
                    pattern=pattern,
                    replacement=replacement
                )
            else:
                print(f"[ERROR] Invalid editfile command: {cmd}")
                print("  Usage: editfile <file_path> <operation> [args...]")
                print("  Operations: append, prepend, replace, insert_after, remove, replace_line")

        else:
            print(f"[WARNING] Unknown command: {cmd}")

    return variables