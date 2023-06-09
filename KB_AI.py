from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores import Chroma
from langchain.chains import RetrievalQA
from langchain.embeddings import OpenAIEmbeddings
from langchain.llms import AzureOpenAI
from datetime import datetime
from tkinter import filedialog
from tkinter import ttk
from tkinter import scrolledtext
import tkinter as tk
import azure.cognitiveservices.speech as speechsdk
import opencc
import configparser
import wikipediaapi
import logging
import shutil
import os

db_dir = 'vs'
kb_dir = 'history'
kb_name = 'wiki.txt'
config_file = 'config.ini'
success = "词条学习成功,可以开始问答啦！"
fail = "词条没有插入，请再试一次！"
insert_info = "请输入内容后再操作！"

font_style = ("微软雅黑", 9)
tile_style = ("微软雅黑", 9,"bold")

config = configparser.ConfigParser()
config.read(config_file)

OPENAI_API_TYPE = "Azure"
OPENAI_API_VERSION = "2023-03-15-preview"

#GPT_NAME = "gpt-35-turbo"
DEPLOYMENT_NAME = config.get('Azure OpenAI','DEPLOYMENT_NAME')
TEXT_EMBED = config.get('Azure OpenAI','TEXT_EMBED')
TEXT_EMBED_MOD = config.get('Azure OpenAI','TEXT_EMBED_MOD')

SPEECH_KEY = config.get('Cognitive Services','SPEECH_KEY')
SPEECH_REGION = config.get('Cognitive Services','SPEECH_REGION')

from dotenv import load_dotenv
os.environ["OPENAI_API_TYPE"] = OPENAI_API_TYPE
os.environ["OPENAI_API_VERSION"] = OPENAI_API_VERSION
os.environ["OPENAI_API_BASE"] = config.get('Azure OpenAI','OPENAI_API_BASE')
os.environ["OPENAI_API_KEY"] = config.get('Azure OpenAI','OPENAI_API_KEY')
load_dotenv()


#对语音服务进行配置
speech_config = speechsdk.SpeechConfig(subscription=SPEECH_KEY, 
                                       region=SPEECH_REGION
                                       )

#文字转化为语音，或者将语音转化为文字.
speech_config.speech_synthesis_voice_name='zh-CN-XiaoyouNeural'
speech_config.speech_recognition_language="zh-CN"

#文字转语音服务
audio_config_txt = speechsdk.audio.AudioOutputConfig(use_default_speaker=True)
speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, 
                                                 audio_config=audio_config_txt
                                                )

#语音识别并转换成文字
audio_config_voice = speechsdk.audio.AudioConfig(use_default_microphone=True)
speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, 
                                               audio_config=audio_config_voice
                                               )

#对学习的文本进行切割及embedding
recurSplitter = RecursiveCharacterTextSplitter(chunk_size=1000,
                                               chunk_overlap=20,
                                               length_function=len
                                               )

embeddings = OpenAIEmbeddings(deployment=TEXT_EMBED, 
                              model=TEXT_EMBED_MOD, 
                              chunk_size = 1
                              )

logging.basicConfig(filename='erro.log', 
                    level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s'
                    )

t2s = opencc.OpenCC('t2s')   

def upload_file():
    try:
        filetypes = [("Text files", "*.txt")]
        filename = filedialog.askopenfilename(filetypes=filetypes)
        wzname = os.path.basename(filename) 
        if not os.path.exists(kb_dir):  # 判断文件夹是否存在
            os.makedirs(kb_dir) 
            info_text.insert(tk.END, f"[{datetime.now().hour:02d}:{datetime.now().minute:02d}:{datetime.now().second:02d}] " + "本地目录创建成功" + '\n')
        shutil.copy(filename, kb_dir)
        info_text.insert(tk.END, f"[{datetime.now().hour:02d}:{datetime.now().minute:02d}:{datetime.now().second:02d}] " + filename + " 文件上传成功" + '\n')
        with open (kb_dir+'/'+wzname, encoding='utf-8') as f:
            content_file = f.read()

        #对文件的大小进行分割裁切，保证符合接口输入大小的要求
        recurse_content = recurSplitter.create_documents([content_file])

        #将embedding后的内容插入向量数据库Chroma中
        vectorestore = Chroma.from_documents(recurse_content, 
                                                embeddings, 
                                                persist_directory=db_dir
                                                )

        vectorestore.persist()
        vectorestore = None
        vectorestore = Chroma (persist_directory = db_dir, 
                                embedding_function=embeddings
                                )
        info_text.insert(tk.END, f"[{datetime.now().hour:02d}:{datetime.now().minute:02d}:{datetime.now().second:02d}] " + "本地" + success + '\n')
    except Exception as e:
        # 处理异常的代码
        info_text.insert(tk.END, f"[{datetime.now().hour:02d}:{datetime.now().minute:02d}:{datetime.now().second:02d}] " + "本地" + fail + '\n')
        logging.info(e)

def create_wiki():
    # 获取文本输入框的内容
    knowledge = entry.get()
    if not knowledge == "": 
        try:
            wiki = wikipediaapi.Wikipedia('zh')
            # 选择要下载的维基百科页面
            page = wiki.page(knowledge)

            # 下载页面内容
            wikipage = t2s.convert(page.text)
            file_name = kb_dir+'/'+ knowledge +".txt"

            # 将页面内容存储在文本文件中
            with open(file_name, 'w', encoding='utf-8') as f:
                f.write(wikipage)
            
            with open(kb_name, 'w', encoding='utf-8') as f:
                f.write(wikipage)

            with open (kb_name, encoding='utf-8') as f:
                content_file = f.read()

            recurse_content = recurSplitter.create_documents([content_file])

            #将embedding后的内容插入向量数据库Chroma中
            vectorestore = Chroma.from_documents(recurse_content, 
                                                embeddings, 
                                                persist_directory=db_dir
                                                )
            vectorestore.persist()
            vectorestore = None
            vectorestore = Chroma (persist_directory = db_dir, 
                                embedding_function=embeddings
                                )
            
            info_text.insert(tk.END, f"[{datetime.now().hour:02d}:{datetime.now().minute:02d}:{datetime.now().second:02d}] " + "维基“" + knowledge + "”" + success + '\n')
            speech_synthesis_result = speech_synthesizer.speak_text_async("维基百科的"+ knowledge + success).get()
            entry.delete(0, tk.END)   
        except Exception as e:
            # 处理异常的代码
            info_text.insert(tk.END, f"[{datetime.now().hour:02d}:{datetime.now().minute:02d}:{datetime.now().second:02d}] " + "维基" + fail + '\n')
            speech_synthesis_result = speech_synthesizer.speak_text_async(fail).get()
            logging.info(e)
    else:
        info_text.insert(tk.END, f"[{datetime.now().hour:02d}:{datetime.now().minute:02d}:{datetime.now().second:02d}] " + insert_info + '\n')
    
def ai_qa():
    try:        
        vectorestore = Chroma(persist_directory = db_dir, embedding_function=embeddings)
        
        chain = RetrievalQA.from_chain_type(llm=AzureOpenAI(model_kwargs={'engine': DEPLOYMENT_NAME}), 
                                        retriever = vectorestore.as_retriever(search_kwargs={"k": 1}), 
                                        chain_type = "stuff"
                                        )
        
        speech_synthesis_result = speech_synthesizer.speak_text_async("请说出您的问题").get()
        speech_recognition_result = speech_recognizer.recognize_once_async().get()
        query = speech_recognition_result.text
        info_text.insert(tk.END, f"[{datetime.now().hour:02d}:{datetime.now().minute:02d}:{datetime.now().second:02d}] " + "语音问题：" + query + '\n')
        if query == "结束。":
            goodbye = "问答结束，齐风再见！"
            info_text.insert(tk.END, f"[{datetime.now().hour:02d}:{datetime.now().minute:02d}:{datetime.now().second:02d}] " + goodbye + '\n')
            speech_synthesis_result = speech_synthesizer.speak_text_async(goodbye).get()
            exit(0)
        if query == "":
            goodbye = "没有收到问题，请尝试再问一次"
            info_text.insert(tk.END,f"[{datetime.now().hour:02d}:{datetime.now().minute:02d}:{datetime.now().second:02d}] " + goodbye + '\n')
            speech_synthesis_result = speech_synthesizer.speak_text_async(goodbye).get()
        else:
            speech = chain.run(query)
            info_text.insert(tk.END, f"[{datetime.now().hour:02d}:{datetime.now().minute:02d}:{datetime.now().second:02d}] " + "AI的回答是：" + speech + '\n')
            speech_synthesis_result = speech_synthesizer.speak_text_async("AI的回答是："+speech).get()
    except Exception as e:
        # 处理异常的代码
        info_text.insert(tk.END, f"[{datetime.now().hour:02d}:{datetime.now().minute:02d}:{datetime.now().second:02d}] " + "系统异常，再试一次吧" + '\n')
        speech_synthesis_result = speech_synthesizer.speak_text_async("系统异常，再试一次吧").get()
        logging.info(e)


def text_qa():
    query = text_entry.get()
    if not query == "": 
        try:
            vectorestore = Chroma(persist_directory = db_dir, embedding_function=embeddings)
            chain = RetrievalQA.from_chain_type(llm=AzureOpenAI(model_kwargs={'engine': DEPLOYMENT_NAME}), 
                                            retriever = vectorestore.as_retriever(search_kwargs={"k": 1}), 
                                            chain_type = "stuff"
                                            ) 
            info_text.insert(tk.END, f"[{datetime.now().hour:02d}:{datetime.now().minute:02d}:{datetime.now().second:02d}] " + "文本问题："+query+'\n')
            if query == "结束":
                goodbye = "问答结束，齐风再见！"
                info_text.insert(tk.END, f"[{datetime.now().hour:02d}:{datetime.now().minute:02d}:{datetime.now().second:02d}] " + goodbye + '\n')
                exit(0)
            else:
                speech = chain.run(query)
                text_entry.delete(0, tk.END)
                info_text.insert(tk.END,f"[{datetime.now().hour:02d}:{datetime.now().minute:02d}:{datetime.now().second:02d}] " + "AI的回答是："+ speech +'\n')
        except Exception as e:
            info_text.insert(tk.END,f"[{datetime.now().hour:02d}:{datetime.now().minute:02d}:{datetime.now().second:02d}] " + "系统异常，再试一次吧" + '\n')
            logging.info(e)
    else:
        info_text.insert(tk.END, f"[{datetime.now().hour:02d}:{datetime.now().minute:02d}:{datetime.now().second:02d}] " + insert_info + '\n')

#用户界面布局
root = tk.Tk()

root.title("Open AI本地知识库语音问答系统 v0.1")
root.geometry("600x405+100+100")
root.resizable(False,False)

# 窗体左侧布局
frame_left = tk.Frame(root)
frame_left.pack(side=tk.LEFT)

# 窗体左侧上部布局
frame_kb = tk.LabelFrame(frame_left, text= "知识学习部分", font=tile_style)
frame_kb.pack(side=tk.TOP, anchor=tk.N, fill=tk.BOTH, padx=10, pady=10)

entry_label = tk.Label(frame_kb, text="输入WIKI词条进行学习：")
entry_label.pack(side="top", anchor=tk.NW, padx=3, pady=3)

entry = tk.Entry(frame_kb, width=30)
entry.pack(side="top", anchor=tk.NW, padx=3, pady=3)

button = tk.Button(frame_kb, text="知识学习", command=create_wiki)
button.pack(side="top", anchor=tk.NE, padx=3, pady=3)

separator = ttk.Separator(frame_kb, orient="horizontal")
separator.pack(fill="x", padx=10, pady=10)

upload_info = tk.Label(frame_kb, text="上传本地文本文件学习：").pack(side="left",  padx=3, pady=5)
upload_button = tk.Button(frame_kb, text="上传文件", command=upload_file).pack(side="right", padx=3, pady=5)

# 窗体左侧下部布局 
frame_ai = tk.LabelFrame(frame_left, text= "知识库AI问答", font=tile_style)
frame_ai.pack(side=tk.TOP, anchor=tk.N, fill=tk.BOTH, padx=10, pady=10)

qa_label = tk.Label(frame_ai, text="点击按钮开始语音问答：")
qa_label.pack(side="top", anchor=tk.W, padx=3, pady=5)

aiqa = tk.Button(frame_ai, text="语音问答", bg="red", fg="white", command=ai_qa)
aiqa.pack(side="top", anchor=tk.E, padx=3, pady=3)

text_label = tk.Label(frame_ai, text="输入您的问题：")
text_label.pack(anchor=tk.NW, padx=3, pady=3)

text_entry = tk.Entry(frame_ai, width=30)
text_entry.pack(side="top", anchor=tk.NW, padx=3, pady=3)

button = tk.Button(frame_ai, text="获取答案", command=text_qa)
button.pack(side="top", anchor=tk.NE, padx=3, pady=3)

# 窗体右侧布局 
frame_right = tk.Frame(root)
frame_right.pack(side=tk.TOP, padx=5)

info_label = tk.Label(frame_right, text="系统信息：", font=tile_style).pack(anchor=tk.W)
user = tk.Label(frame_right, text="Created by Eric Qi @ 2023"+"\n"+"Powered by Open AI GPT3.5", fg="blue", font=("微软雅黑", 8)).pack(side="bottom", pady=3, anchor=tk.E)

info_text = scrolledtext.ScrolledText(frame_right, font=font_style, bg='#F0F0F0', fg="#000C7B")
info_text.pack(side=tk.LEFT, fill=tk.BOTH)

root.mainloop()