from optimum.onnxruntime import ORTModelForCausalLM
from transformers import AutoTokenizer

model_id = "openai/gpt-oss-20b"
save_dir = "./triton/models/gpt-oss20b/1"

model = ORTModelForCausalLM.from_pretrained(model_id, export=True, use_cache=False)
tokenizer = AutoTokenizer.from_pretrained(model_id)
model.save_pretrained(save_dir)
tokenizer.save_pretrained(save_dir)
