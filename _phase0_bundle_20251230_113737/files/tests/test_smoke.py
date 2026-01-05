from laptop_agents.core.runner import Runner

def test_runner_smoke(tmp_path):
    r = Runner(data_dir=str(tmp_path))
    out = r.run("planner", "Create a checklist for backing up files")
    assert "PLAN for:" in out
