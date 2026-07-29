import json
import os

from utils.config import Config


def test_configs_dir_is_isolated_from_repo(isolated_singletons, monkeypatch):
    configs_dir_env = os.environ["CACHE_MANAGER_CONFIGS_DIR"]

    import utils.config as cfg
    cfg_instance = cfg.config

    assert cfg_instance.configs_dir == configs_dir_env
    assert cfg_instance.configs_dir != Config.CONFIGS_DIR_LOC
    assert cfg_instance.config_path.startswith(configs_dir_env)


def test_set_and_save_config_value_roundtrip(isolated_singletons):
    import utils.config as cfg
    cfg_instance = cfg.config

    changed = cfg_instance.set_config_value("foreground_color", "black")
    assert changed is True
    assert cfg_instance.has_changes()

    assert cfg_instance.save_config() is True
    assert not cfg_instance.has_changes()

    with open(cfg_instance.config_path, "r", encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["foreground_color"] == "black"

    # Nothing should have leaked into the real repo configs directory.
    real_config_json = os.path.join(Config.CONFIGS_DIR_LOC, "config.json")
    if os.path.exists(real_config_json):
        with open(real_config_json, "r", encoding="utf-8") as f:
            real_saved = json.load(f)
        assert real_saved.get("foreground_color") != "black"


def test_create_from_example_populates_config_json(tmp_path, monkeypatch):
    """Self-contained: uses its own scratch configs dir (rather than the
    fixture-provided one, which already has a config.json) so the "no
    config.json yet" path is actually exercised."""
    configs_dir = tmp_path / "fresh_configs"
    configs_dir.mkdir()
    real_example = os.path.join(Config.CONFIGS_DIR_LOC, "config_example.json")
    with open(real_example, "r", encoding="utf-8") as f:
        example_contents = f.read()
    (configs_dir / "config_example.json").write_text(example_contents, encoding="utf-8")

    monkeypatch.setenv("CACHE_MANAGER_CONFIGS_DIR", str(configs_dir))
    config = Config()

    assert config.create_from_example() is True
    assert os.path.exists(configs_dir / "config.json")
    assert config.config_path == str(configs_dir / "config.json")
    # The temporary swap file used internally by save_config() must be
    # cleaned up, and must never have been written to the real configs dir.
    leftover_swap_files = [p for p in os.listdir(configs_dir) if p.startswith("config_swap_")]
    assert leftover_swap_files == []
