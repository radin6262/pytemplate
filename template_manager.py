"""Template manager for PyTemplate - Interactive template navigator."""

import click
import os
import shutil
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime


def color(text: str, fg: str = None, bold: bool = False, dim: bool = False) -> str:
    """Apply color to text using Click."""
    return click.style(text, fg=fg, bold=bold, dim=dim)


class TemplateManager:
    """Manages PyTemplate templates with metadata and organization."""

    def __init__(self, templates_dir: Path):
        self.templates_dir = templates_dir
        self.metadata_file = templates_dir / "registry.json"
        self.metadata = self._load_metadata()

    def _load_metadata(self) -> Dict:
        """Load template metadata from registry.json."""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r') as f:
                    return json.load(f)
            except:
                return {"templates": {}}
        return {"templates": {}}

    def _save_metadata(self):
        """Save template metadata to registry.json."""
        with open(self.metadata_file, 'w') as f:
            json.dump(self.metadata, f, indent=2)

    def _extract_metadata(self, template_path: Path) -> Dict:
        """Extract metadata from a .setup file."""
        metadata = {
            "name": template_path.stem,
            "description": "",
            "author": "",
            "version": "1.0.0",
            "category": "uncategorized",
            "tags": [],
            "created": datetime.now().isoformat(),
            "modified": datetime.now().isoformat(),
            "type": "local",
            "path": str(template_path)
        }

        try:
            content = template_path.read_text()
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('# @'):
                    parts = line[3:].split(':', 1)
                    if len(parts) == 2:
                        key = parts[0].strip()
                        value = parts[1].strip()
                        if key == 'template':
                            metadata['name'] = value
                        elif key == 'description':
                            metadata['description'] = value
                        elif key == 'author':
                            metadata['author'] = value
                        elif key == 'version':
                            metadata['version'] = value
                        elif key == 'category':
                            metadata['category'] = value
                        elif key == 'tags':
                            metadata['tags'] = [t.strip() for t in value.split(',')]
        except:
            pass

        return metadata

    def list_templates(self) -> List[Dict]:
        """List all templates from the templates directory."""
        templates = []

        # Scan the templates directory for .setup files
        for template_file in self.templates_dir.glob("*.setup"):
            # Skip registry.json and other non-template files
            if template_file.name == "registry.json":
                continue
            metadata = self._extract_metadata(template_file)
            templates.append(metadata)

        return sorted(templates, key=lambda x: x["name"])

    def get_template(self, name: str) -> Optional[Dict]:
        """Get template metadata by name."""
        templates = self.list_templates()
        for t in templates:
            if t["name"] == name:
                return t
        return None

    def remove_template(self, name: str) -> bool:
        """Remove a template by name."""
        template = self.get_template(name)
        if not template:
            click.echo(color(f"Template '{name}' not found.", fg="red"))
            return False

        if not click.confirm(color(f"Remove template '{name}'?", fg="yellow")):
            return False

        template_path = Path(template["path"])
        if template_path.exists():
            template_path.unlink()
            click.echo(color(f"[OK] Removed: {name}", fg="green"))
            return True

        click.echo(color(f"Template file not found: {template_path}", fg="red"))
        return False

    def rename_template(self, old_name: str, new_name: str) -> bool:
        """Rename a template."""
        template = self.get_template(old_name)
        if not template:
            click.echo(color(f"Template '{old_name}' not found.", fg="red"))
            return False

        if self.get_template(new_name):
            click.echo(color(f"Template '{new_name}' already exists.", fg="red"))
            return False

        old_path = Path(template["path"])
        new_path = old_path.parent / f"{new_name}.setup"

        if old_path.exists():
            old_path.rename(new_path)
            click.echo(color(f"[OK] Renamed: {old_name} -> {new_name}", fg="green"))
            return True

        click.echo(color(f"Template file not found: {old_path}", fg="red"))
        return False

    def export_template(self, name: str, output_path: Path) -> bool:
        """Export a template to a file."""
        template = self.get_template(name)
        if not template:
            click.echo(color(f"Template '{name}' not found.", fg="red"))
            return False

        source_path = Path(template["path"])
        if not source_path.exists():
            click.echo(color(f"Template file not found: {source_path}", fg="red"))
            return False

        try:
            shutil.copy2(source_path, output_path)
            click.echo(color(f"[OK] Exported: {output_path}", fg="green"))
            return True
        except Exception as e:
            click.echo(color(f"Error exporting template: {e}", fg="red"))
            return False

    def import_template(self, source_path: Path) -> bool:
        """Import a template from a file."""
        if not source_path.exists():
            click.echo(color(f"File not found: {source_path}", fg="red"))
            return False

        if source_path.suffix != '.setup':
            click.echo(color("File must have .setup extension.", fg="red"))
            return False

        name = source_path.stem
        dest_path = self.templates_dir / f"{name}.setup"

        if dest_path.exists():
            if not click.confirm(color(f"Template '{name}' already exists. Overwrite?", fg="yellow")):
                return False

        try:
            shutil.copy2(source_path, dest_path)
            click.echo(color(f"[OK] Imported: {name}", fg="green"))
            return True
        except Exception as e:
            click.echo(color(f"Error importing template: {e}", fg="red"))
            return False


def launch_template_builder(template_name: str = None):
    """Launch the template builder with optional template name."""
    script_path = Path(__file__).parent / "cli.py"

    if template_name:
        cmd = [sys.executable, str(script_path), "buildtemplate", template_name]
    else:
        name = click.prompt(color("Template name", fg="cyan"), type=str)
        cmd = [sys.executable, str(script_path), "buildtemplate", name]

    click.echo(color(f"\nLaunching template builder...", fg="yellow"))
    click.echo(color(f"Running: {' '.join(cmd)}\n", dim=True))

    try:
        subprocess.run(cmd)
        return True
    except Exception as e:
        click.echo(color(f"Error launching template builder: {e}", fg="red"))
        return False


def launch_template_downloader():
    """Launch the template downloader wizard."""
    script_path = Path(__file__).parent / "downloadtemplate.py"

    if not script_path.exists():
        click.echo(color(f"Download template wizard not found at: {script_path}", fg="red"))

    click.echo(color(f"\nLaunching template downloader...", fg="yellow"))
    click.echo(color(f"Running: {script_path}\n", dim=True))

    try:
        subprocess.run([sys.executable, str(script_path)])
        return True
    except Exception as e:
        click.echo(color(f"Error launching template downloader: {e}", fg="red"))
        return False



    script_path.write_text(wizard_content)
    click.echo(color(f"[OK] Created download template wizard at: {script_path}", fg="green"))


def interactive_template_manager(templates_dir: Path):
    """Run the interactive template navigator."""
    manager = TemplateManager(templates_dir)

    while True:
        click.echo("\n" + color("=" * 60, fg="blue", bold=True))
        click.echo(color("TEMPLATE NAVIGATOR", fg="cyan", bold=True))
        click.echo(color("=" * 60, fg="blue", bold=True))

        # Show templates with numbers
        templates = manager.list_templates()
        if not templates:
            click.echo(color("  No templates found.", fg="yellow"))
            click.echo("\n  " + color("[c]", fg="green", bold=True) + " Create new template")
            click.echo("  " + color("[i]", fg="green", bold=True) + " Import template")
            click.echo("  " + color("[w]", fg="cyan", bold=True) + " Download template (from registry)")
            click.echo("  " + color("[q]", fg="red", bold=True) + " Quit")
            choice = click.prompt("\nChoice", default="q", show_default=False)

            if choice.lower() == 'c':
                launch_template_builder()
                continue
            elif choice.lower() == 'i':
                path = click.prompt("File path to import", type=str)
                manager.import_template(Path(path))
                continue
            elif choice.lower() == 'w':
                launch_template_downloader()
                continue
            elif choice.lower() == 'q':
                break
            continue

        click.echo("\n" + color("TEMPLATES:", fg="yellow", bold=True))
        click.echo(color("-" * 60, fg="blue"))
        for i, t in enumerate(templates, 1):
            desc = f" - {t['description'][:40]}" if t.get('description') else ""
            click.echo(f"  {color(f'[{i:2d}]', fg='cyan')} {color(t['name'], fg='white', bold=True):<20}{color(desc, fg='white', dim=True)}")

        click.echo("\n" + color("-" * 60, fg="blue"))
        click.echo(color("ACTIONS:", fg="yellow", bold=True))
        click.echo("  " + color("[number]", fg="cyan") + "  Select template to view/use")
        click.echo("  " + color("[c]", fg="green", bold=True) + "       Create new template")
        click.echo("  " + color("[d]", fg="red", bold=True) + "       Delete a template")
        click.echo("  " + color("[r]", fg="magenta", bold=True) + "       Rename a template")
        click.echo("  " + color("[e]", fg="blue", bold=True) + "       Export a template")
        click.echo("  " + color("[i]", fg="green", bold=True) + "       Import a template")
        click.echo("  " + color("[w]", fg="cyan", bold=True) + "       Download template (from registry)")
        click.echo("  " + color("[q]", fg="red", bold=True) + "       Quit")
        click.echo(color("=" * 60, fg="blue", bold=True))

        choice = click.prompt("\nChoice", default="q", show_default=False)

        if choice.lower() == 'q':
            break

        elif choice.lower() == 'c':
            launch_template_builder()
            continue

        elif choice.lower() == 'w':
            launch_template_downloader()
            continue

        elif choice.lower() == 'd':
            name = click.prompt(color("Template name to delete", fg="red"), type=str)
            manager.remove_template(name)
            continue

        elif choice.lower() == 'r':
            old_name = click.prompt(color("Current template name", fg="magenta"), type=str)
            new_name = click.prompt(color("New template name", fg="magenta"), type=str)
            manager.rename_template(old_name, new_name)
            continue

        elif choice.lower() == 'e':
            name = click.prompt(color("Template name to export", fg="blue"), type=str)
            output_path = Path(click.prompt("Output path", type=str))
            manager.export_template(name, output_path)
            continue

        elif choice.lower() == 'i':
            source_path = Path(click.prompt("File path to import", type=str))
            manager.import_template(source_path)
            continue

        else:
            # Try to select by number
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(templates):
                    template = templates[idx]
                    click.echo("\n" + color("=" * 60, fg="blue", bold=True))
                    click.echo(color(f"TEMPLATE: {template['name']}", fg="cyan", bold=True))
                    click.echo(color("=" * 60, fg="blue", bold=True))

                    if template.get('description'):
                        click.echo(color(f"  Description: ", fg="yellow") + color(template['description'], fg="white"))
                    if template.get('author'):
                        click.echo(color(f"  Author: ", fg="yellow") + color(template['author'], fg="white"))
                    if template.get('version'):
                        click.echo(color(f"  Version: ", fg="yellow") + color(template['version'], fg="white"))
                    if template.get('category'):
                        click.echo(color(f"  Category: ", fg="yellow") + color(template['category'], fg="white"))
                    if template.get('tags'):
                        click.echo(color(f"  Tags: ", fg="yellow") + color(', '.join(template['tags']), fg="white"))

                    # Show template content preview
                    template_path = Path(template['path'])
                    if template_path.exists():
                        content = template_path.read_text()
                        lines = content.split('\n')
                        dirs = sum(1 for l in lines if l.strip().endswith('/') and not l.strip().startswith('['))
                        files = sum(1 for l in lines if ':' in l and not l.strip().startswith('['))

                        click.echo(color(f"\n  Statistics:", fg="yellow"))
                        click.echo(color(f"    Directories: ", fg="white", dim=True) + color(str(dirs), fg="white"))
                        click.echo(color(f"    Files: ", fg="white", dim=True) + color(str(files), fg="white"))

                        if '[setup]' in content:
                            click.echo(color(f"    Setup commands: ", fg="white", dim=True) + color("Yes", fg="green"))

                        click.echo(color("\n  Preview (first 20 lines):", fg="yellow"))
                        click.echo(color("  " + "-" * 40, fg="blue"))
                        preview = '\n'.join(lines[:20])
                        for line in preview.split('\n'):
                            click.echo(color(f"  {line}", fg="white", dim=True))
                        if len(lines) > 20:
                            click.echo(color("  ...", fg="white", dim=True))
                        click.echo(color("  " + "-" * 40, fg="blue"))

                    click.echo("\n" + color("ACTIONS:", fg="yellow", bold=True))
                    click.echo("  " + color("[u]", fg="green", bold=True) + " Use this template (create project)")
                    click.echo("  " + color("[n]", fg="cyan", bold=True) + " Create new template (launch builder)")
                    click.echo("  " + color("[v]", fg="blue", bold=True) + " View full template")
                    click.echo("  " + color("[b]", fg="magenta", bold=True) + " Back to template list")

                    action = click.prompt("\nAction", default="b", show_default=False)

                    if action.lower() == 'u':
                        project_name = click.prompt(color("Project name", fg="green"), type=str)
                        click.echo(color(f"\nRunning: pytemplate create {project_name} --template {template['name']}", fg="yellow"))
                        script_path = Path(__file__).parent / "cli.py"
                        cmd = [sys.executable, str(script_path), "create", project_name, "--template", template['name']]
                        try:
                            subprocess.run(cmd)
                        except Exception as e:
                            click.echo(color(f"Error: {e}", fg="red"))
                        continue
                    elif action.lower() == 'n':
                        launch_template_builder()
                        continue
                    elif action.lower() == 'v':
                        click.echo("\n" + color("=" * 60, fg="blue", bold=True))
                        click.echo(color(f"FULL TEMPLATE: {template['name']}", fg="cyan", bold=True))
                        click.echo(color("=" * 60, fg="blue", bold=True))
                        click.echo(color(template_path.read_text(), fg="white"))
                        click.echo(color("=" * 60, fg="blue", bold=True))
                        click.pause(color("Press Enter to continue...", fg="white", dim=True))
                    else:
                        continue
                else:
                    click.echo(color("Invalid selection.", fg="red"))
            except ValueError:
                click.echo(color(f"Unknown command: {choice}", fg="red"))


def register_commands(cli_group):
    """Register template manager command with the CLI group."""

    @cli_group.command()
    def templates():
        """Open interactive template navigator."""
        templates_dir = Path(__file__).parent / "templates"
        interactive_template_manager(templates_dir)