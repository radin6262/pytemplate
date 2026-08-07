"""CLI-based file system navigator for template builder."""

import click
import shutil
import tempfile
import os
from pathlib import Path
from typing import List, Optional, Tuple

class CLIFileManager:
    """CLI-based file manager with navigation and file operations."""

    def __init__(self, template_name: str, initial_dir: str = "."):
        self.template_name = template_name
        self.base_dir = Path(initial_dir).resolve()

        # Create temp directory for the template
        self.temp_dir = Path(tempfile.mkdtemp()) / template_name
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # Start at the temp directory root
        self.current_dir = self.temp_dir

        # Track selected files - automatically add created files
        self.selected_paths = []
        self.should_cleanup = True

    def run(self) -> List[str]:
        """
        Run the file manager interface.

        Returns:
            List of selected file paths
        """
        click.echo("\n" + "=" * 60)
        click.echo(f"FILE MANAGER - {self.template_name}")
        click.echo("=" * 60)
        click.echo(f"Working in: {self.temp_dir}")
        click.echo("Create your project structure here. Files/directories you")
        click.echo("create will be added to your template.")
        click.echo("NOTE: Created files are automatically selected!")
        click.echo("=" * 60)

        return self._main_menu()

    def _main_menu(self) -> List[str]:
        """Main file manager menu."""
        selected = self.selected_paths

        while True:
            self._display_current_directory()
            items = self._get_directory_items()

            click.echo("\nCOMMANDS:")
            click.echo("  [n] Navigate into directory")
            click.echo("  [..] Go up one level")
            click.echo("  [d] Create directory")
            click.echo("  [f] Create file (auto-selected)")
            click.echo("  [s] Select/unselect file(s) for template")
            click.echo("  [v] View file content")
            click.echo("  [e] Edit file")
            click.echo("  [r] Rename/Delete item")
            click.echo("  [c] Change directory by path")
            click.echo("  [p] Preview template structure")
            click.echo("  [q] Quit and return selected files")

            # Show items with numbers
            click.echo("\nITEMS:")
            if self.current_dir != self.temp_dir:
                click.echo("  [..] 📁 .. (parent directory)")

            # Show items
            if items:
                for i, item in enumerate(items, 1):
                    icon = "📁" if item[1] else "📄"
                    file_path = str(self.current_dir / item[0])
                    if file_path in selected:
                        icon = "★ " + icon
                    click.echo(f"  [{i:2d}] {icon} {item[0]}")
            else:
                click.echo("  (empty directory)")

            if selected:
                click.echo(f"\nSelected: {len(selected)} files")
                # Show selected files
                for f in selected:
                    click.echo(f"  ✓ {Path(f).name}")

            choice = click.prompt("\nEnter number, or command", default="", show_default=False)

            if choice.lower() == 'q':
                # Return selected files
                return selected
            elif choice.lower() == '..':
                if self.current_dir != self.temp_dir:
                    self.current_dir = self.current_dir.parent
            elif choice.lower() == 'd':
                self._create_directory()
            elif choice.lower() == 'f':
                self._create_file(selected)
            elif choice.lower() == 's':
                self._select_files(items, selected)
            elif choice.lower() == 'v':
                self._view_file(items)
            elif choice.lower() == 'e':
                self._edit_file(items)
            elif choice.lower() == 'r':
                self._rename_or_delete(items, selected)
            elif choice.lower() == 'c':
                self._change_directory()
            elif choice.lower() == 'n':
                self._navigate_to_item(items)
            elif choice.lower() == 'p':
                self._preview_structure()
            else:
                # Try to navigate by number or select file
                if choice.isdigit():
                    try:
                        idx = int(choice) - 1
                        if 0 <= idx < len(items):
                            item_name, is_dir = items[idx]
                            if is_dir:
                                self.current_dir = self.current_dir / item_name
                            else:
                                # Show file content
                                file_path = self.current_dir / item_name
                                self._show_file_content(file_path)
                        else:
                            click.echo("  Invalid selection.")
                    except ValueError:
                        click.echo(f"  Invalid selection.")
                else:
                    click.echo(f"  Unknown command: {choice}")

    def _display_current_directory(self):
        """Display the current directory path."""
        # Show relative path from temp_dir
        try:
            rel_path = self.current_dir.relative_to(self.temp_dir)
            if str(rel_path) == '.':
                display_path = "/"
            else:
                display_path = f"/{rel_path}"
        except ValueError:
            display_path = str(self.current_dir)

        click.echo("\n" + "=" * 60)
        click.echo(f"📂 {self.template_name}{display_path}")
        click.echo("=" * 60)

    def _get_directory_items(self) -> List[Tuple[str, bool]]:
        """Get items in current directory."""
        items = []
        try:
            for item in sorted(self.current_dir.iterdir()):
                if item.name.startswith('.'):
                    continue
                is_dir = item.is_dir()
                items.append((item.name, is_dir))
        except PermissionError:
            click.echo("  Permission denied to read this directory.")
        except FileNotFoundError:
            click.echo("  Directory not found. Returning to root.")
            self.current_dir = self.temp_dir
        return items

    def _navigate_to_item(self, items: List[Tuple[str, bool]]):
        """Navigate to a directory."""
        dirs = [(name, is_dir) for name, is_dir in items if is_dir]
        if not dirs:
            click.echo("  No directories in this location.")
            return

        click.echo("Select directory to navigate into:")
        for i, (name, _) in enumerate(dirs, 1):
            click.echo(f"  [{i}] {name}")

        choice = click.prompt("Number", default="", show_default=False)
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(dirs):
                name, _ = dirs[idx]
                self.current_dir = self.current_dir / name
            else:
                click.echo("  Invalid selection.")
        except ValueError:
            click.echo("  Please enter a number.")

    def _create_directory(self):
        """Create a new directory."""
        name = click.prompt("Directory name (e.g., src/)", default="", show_default=False)
        if name:
            # Remove trailing slash if present
            name = name.rstrip('/')
            # Remove any path separators - only allow single directory names
            if '/' in name or '\\' in name:
                click.echo("  Please enter a single directory name (not a path).")
                return

            new_dir = self.current_dir / name
            try:
                new_dir.mkdir()
                click.echo(f"  ✓ Created directory: {name}/")
            except FileExistsError:
                click.echo(f"  Directory '{name}' already exists.")
            except Exception as e:
                click.echo(f"  Error creating directory: {e}")

    def _create_file(self, selected: List[str]):
        """Create a new file and automatically add to selection."""
        name = click.prompt("File name (e.g., main.py)", default="", show_default=False)
        if name:
            # Remove any path separators - only allow single file names
            if '/' in name or '\\' in name:
                click.echo("  Please enter a single file name (not a path).")
                return

            new_file = self.current_dir / name
            try:
                content = click.prompt("File content (or @reference)", default="", show_default=False)
                new_file.write_text(content if content else "")
                click.echo(f"  ✓ Created file: {name}")

                # Auto-select the created file
                file_path = str(new_file)
                if file_path not in selected:
                    selected.append(file_path)
                    click.echo(f"  ✓ Auto-selected: {name}")
                else:
                    click.echo(f"  ⚠ File already selected: {name}")
            except Exception as e:
                click.echo(f"  Error creating file: {e}")

    def _select_files(self, items: List[Tuple[str, bool]], selected: List[str]):
        """Select/unselect files for the template."""
        files = [(name, False) for name, is_dir in items if not is_dir]

        if not files:
            click.echo("  No files in this directory.")
            return

        click.echo("\nSelect/unselect files:")
        click.echo("Enter numbers separated by commas (e.g., 1,3,5) or ranges (e.g., 1-5)")
        click.echo("  [a] Select all files")
        click.echo("  [c] Clear selection")
        click.echo("  [d] Done selecting")

        for i, (name, _) in enumerate(files, 1):
            file_path = str(self.current_dir / name)
            selected_mark = "✓" if file_path in selected else " "
            click.echo(f"  [{selected_mark}] [{i}] {name}")

        choice = click.prompt("Selection", default="d", show_default=False)

        if choice.lower() == 'a':
            # Select all files
            for name, _ in files:
                file_path = str(self.current_dir / name)
                if file_path not in selected:
                    selected.append(file_path)
            click.echo(f"  Selected {len(files)} files")
        elif choice.lower() == 'c':
            # Clear selection of current directory files
            for name, _ in files:
                file_path = str(self.current_dir / name)
                if file_path in selected:
                    selected.remove(file_path)
            click.echo("  Selection cleared")
        elif choice.lower() == 'd':
            return
        else:
            # Parse selection
            parts = choice.split(',')
            for part in parts:
                part = part.strip()
                if '-' in part:
                    try:
                        start, end = map(int, part.split('-'))
                        for i in range(start - 1, end):
                            if 0 <= i < len(files):
                                name, _ = files[i]
                                file_path = str(self.current_dir / name)
                                if file_path in selected:
                                    selected.remove(file_path)
                                    click.echo(f"  Deselected: {name}")
                                else:
                                    selected.append(file_path)
                                    click.echo(f"  Selected: {name}")
                    except ValueError:
                        pass
                else:
                    try:
                        idx = int(part) - 1
                        if 0 <= idx < len(files):
                            name, _ = files[idx]
                            file_path = str(self.current_dir / name)
                            if file_path in selected:
                                selected.remove(file_path)
                                click.echo(f"  Deselected: {name}")
                            else:
                                selected.append(file_path)
                                click.echo(f"  Selected: {name}")
                    except ValueError:
                        pass
            click.echo(f"  Updated selection")

    def _view_file(self, items: List[Tuple[str, bool]]):
        """View file content."""
        files = [(name, False) for name, is_dir in items if not is_dir]
        if not files:
            click.echo("  No files in this directory.")
            return

        click.echo("\nSelect file to view:")
        for i, (name, _) in enumerate(files, 1):
            click.echo(f"  [{i}] {name}")

        choice = click.prompt("Number", default="", show_default=False)
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(files):
                file_path = self.current_dir / files[idx][0]
                self._show_file_content(file_path)
            else:
                click.echo("  Invalid selection.")
        except ValueError:
            click.echo("  Please enter a number.")

    def _show_file_content(self, file_path: Path):
        """Show content of a file."""
        try:
            if file_path.stat().st_size > 1024 * 10:  # > 10KB
                click.echo(f"  File is too large to display ({file_path.stat().st_size} bytes)")
                return

            content = file_path.read_text()
            click.echo("\n" + "-" * 40)
            click.echo(f"📄 {file_path.name}:")
            click.echo("-" * 40)
            click.echo(content[:500])  # Show first 500 chars
            if len(content) > 500:
                click.echo("... (truncated)")
            click.echo("-" * 40)
        except Exception as e:
            click.echo(f"  Error reading file: {e}")

    def _edit_file(self, items: List[Tuple[str, bool]]):
        """Edit a file."""
        files = [(name, False) for name, is_dir in items if not is_dir]
        if not files:
            click.echo("  No files in this directory.")
            return

        click.echo("\nSelect file to edit:")
        for i, (name, _) in enumerate(files, 1):
            click.echo(f"  [{i}] {name}")

        choice = click.prompt("Number", default="", show_default=False)
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(files):
                file_path = self.current_dir / files[idx][0]
                current_content = file_path.read_text() if file_path.exists() else ""
                click.echo(f"\nCurrent content:\n{'-' * 40}")
                click.echo(current_content[:200])
                if len(current_content) > 200:
                    click.echo("...")
                click.echo("-" * 40)

                new_content = click.prompt("New content (or @reference)", default="", show_default=False)
                if new_content:
                    file_path.write_text(new_content)
                    click.echo(f"  ✓ Updated: {file_path.name}")
                else:
                    click.echo("  No changes made.")
            else:
                click.echo("  Invalid selection.")
        except ValueError:
            click.echo("  Please enter a number.")

    def _rename_or_delete(self, items: List[Tuple[str, bool]], selected: List[str]):
        """Rename or delete a file/directory."""
        click.echo("\nSelect item to rename/delete:")
        for i, (name, is_dir) in enumerate(items, 1):
            icon = "📁" if is_dir else "📄"
            click.echo(f"  [{i}] {icon} {name}")

        choice = click.prompt("Number", default="", show_default=False)
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(items):
                name, is_dir = items[idx]
                item_path = self.current_dir / name

                click.echo(f"\nItem: {name}")
                click.echo("  [r] Rename")
                click.echo("  [d] Delete")

                action = click.prompt("Action", default="", show_default=False)
                if action.lower() == 'r':
                    new_name = click.prompt("New name", default="", show_default=False)
                    if new_name:
                        # Remove any path separators
                        new_name = new_name.replace('/', '').replace('\\', '')
                        if new_name:
                            new_path = self.current_dir / new_name
                            old_path_str = str(item_path)
                            item_path.rename(new_path)
                            # Update selection if file was selected
                            if old_path_str in selected:
                                selected.remove(old_path_str)
                                selected.append(str(new_path))
                            click.echo(f"  ✓ Renamed to: {new_name}")
                        else:
                            click.echo("  Invalid name.")
                elif action.lower() == 'd':
                    if click.confirm(f"Delete {name}?"):
                        old_path_str = str(item_path)
                        if is_dir:
                            # Remove directory and its contents
                            shutil.rmtree(item_path)
                        else:
                            item_path.unlink()
                        # Remove from selection if it was selected
                        if old_path_str in selected:
                            selected.remove(old_path_str)
                        click.echo(f"  ✓ Deleted: {name}")
                else:
                    click.echo("  Invalid action.")
            else:
                click.echo("  Invalid selection.")
        except ValueError:
            click.echo("  Please enter a number.")
        except Exception as e:
            click.echo(f"  Error: {e}")

    def _change_directory(self):
        """Change to a different directory within the temp folder."""
        click.echo(f"Current temp directory: {self.temp_dir}")
        click.echo("Enter a relative path from the temp directory (e.g., src/, tests/)")
        new_path = click.prompt("Path", default=".", show_default=False)

        try:
            if new_path == '.':
                self.current_dir = self.temp_dir
            elif new_path == '..':
                self.current_dir = self.temp_dir
            else:
                # Remove leading/trailing slashes
                new_path = new_path.strip('/\\')
                path = self.temp_dir / new_path
                if path.exists() and path.is_dir():
                    self.current_dir = path.resolve()
                else:
                    click.echo(f"  Directory doesn't exist: {new_path}")
                    if click.confirm("Create it?"):
                        path.mkdir(parents=True)
                        self.current_dir = path
                        click.echo(f"  ✓ Created and navigated to: {new_path}")
        except Exception as e:
            click.echo(f"  Error: {e}")

    def _preview_structure(self):
        """Preview the current template structure."""
        click.echo("\n[TEMPLATE STRUCTURE PREVIEW]")
        click.echo("=" * 50)

        if not any(self.temp_dir.iterdir()):
            click.echo("  No files or directories created yet.")
            return

        # Build tree structure
        self._print_tree(self.temp_dir, "")
        click.echo("=" * 50)

    def _print_tree(self, path: Path, prefix: str, is_last: bool = True):
        """Print directory tree structure."""
        # Get items
        items = []
        try:
            for item in sorted(path.iterdir()):
                if item.name.startswith('.'):
                    continue
                items.append(item)
        except PermissionError:
            return

        if not items:
            return

        for i, item in enumerate(items):
            is_last_item = (i == len(items) - 1)
            connector = "└── " if is_last_item else "├── "
            # Check if file is selected
            file_path = str(item)
            if file_path in self.selected_paths:
                click.echo(f"{prefix}{connector}★ {item.name}{'/' if item.is_dir() else ''}")
            else:
                click.echo(f"{prefix}{connector}{item.name}{'/' if item.is_dir() else ''}")

            if item.is_dir():
                new_prefix = prefix + ("    " if is_last_item else "│   ")
                self._print_tree(item, new_prefix, is_last_item)

    def cleanup(self):
        """Clean up the temporary directory."""
        if self.should_cleanup:
            shutil.rmtree(self.temp_dir, ignore_errors=True)