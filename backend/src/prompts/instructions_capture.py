import yaml

with open("system_prompt.yaml", "r") as f:
    config = yaml.safe_load(f)

system_prompt = config["system_prompt"]
