import torch
# from auto_gptq import AutoGPTQForCausalLM
from langchain_community.embeddings import HuggingFaceInstructEmbeddings
from langchain import HuggingFacePipeline, PromptTemplate
from langchain.chains import RetrievalQA
from transformers import AutoTokenizer, TextStreamer, pipeline, AutoModelForCausalLM
from langchain.vectorstores import Chroma
from langchain.embeddings import HuggingFaceInstructEmbeddings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"

print(DEVICE, torch.cuda.is_available())
print(torch.version.cuda)

embeddings = HuggingFaceInstructEmbeddings(
    model_name="hkunlp/instructor-large", model_kwargs={"device": DEVICE}
)

db = Chroma(persist_directory="db", embedding_function=embeddings)


# model_name_or_path = "TheBloke/Llama-2-13B-chat-GPTQ"
model_name_or_path = "TheBloke/Llama-2-7b-Chat-GPTQ"
# model_name_or_path = "MBZUAI/LaMini-Flan-T5-783M"
model_basename = "model"

tokenizer = AutoTokenizer.from_pretrained(model_name_or_path, use_fast=True)

model = AutoModelForCausalLM.from_pretrained(
    model_name_or_path,
    device_map="auto",
    trust_remote_code=True,
    # revision="main",    
    revision="gptq-4bit-128g-actorder_True",    
    use_safetensors=True,
)


print("model is ", model)

DEFAULT_SYSTEM_PROMPT = """
You are a helpful, respectful and honest assistant. Always answer as helpfully as possible, while being safe. Your answers should not include any harmful, unethical, racist, sexist, toxic, dangerous, or illegal content. Please ensure that your responses are socially unbiased, concise and positive in nature.

If a question does not make any sense, or is not factually coherent, explain why instead of answering something not correct. If you don't know the answer to a question, please don't share false information.
""".strip()

print(DEFAULT_SYSTEM_PROMPT)


def generate_prompt(prompt: str, system_prompt: str = DEFAULT_SYSTEM_PROMPT) -> str:
    return f"""
[INST] <>
{system_prompt}
<>

{prompt} [/INST]
""".strip()


streamer = TextStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)

text_pipeline = pipeline(
    "text-generation",
    model=model,
    tokenizer=tokenizer,
    max_new_tokens=1024,
    temperature=0,
    top_p=0.95,
    repetition_penalty=1.15,
    streamer=streamer,
)

llm = HuggingFacePipeline(pipeline=text_pipeline, model_kwargs={"temperature": 0})

SYSTEM_PROMPT = "Use the following pieces of context to answer the question in short concise manner at the end. If you don't know the answer, just say that you don't know, don't try to make up an answer."

template = generate_prompt(
    """{context} 
    Question: {question}""",
    system_prompt=SYSTEM_PROMPT,
)

prompt = PromptTemplate(template=template, input_variables=["context", "question"])

qa_chain = RetrievalQA.from_chain_type(
    llm=llm,
    chain_type="stuff",
    retriever=db.as_retriever(search_kwargs={"k": 2}),
    return_source_documents=True,
    chain_type_kwargs={"prompt": prompt},
)


app = FastAPI()

origins = [
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def llmQuery(query: str):
    print("query is", query)    
    result = qa_chain(query)
    print(result)
    return {"result" : result}
