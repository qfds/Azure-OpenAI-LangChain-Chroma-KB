# Azure-OpenAI-LangChain-Chroma-KB
## 介绍
这个是我第一个AI的小demo项目，主要目的是：让AI对维基百科上面的一些指定词条或者本地的文本知识库进行学习，然后通过语音或者文字的方式向AI进行提问。
程序用Pyhton开发，调用Azure的OpenAI接口并使用tkinter编写的GUI界面，运行后是一个window程序，如下所示：

<div align=center><img src="https://github.com/qfds/Azure-OpenAI-LangChain-Chroma-KB/blob/main/img/screenshot.png">
  <p>程序界面展示</p>
</div>

## 程序说明
<div align=center><img src="https://github.com/qfds/Azure-OpenAI-LangChain-Chroma-KB/blob/main/img/diagram.png">
  <p>程序流程图</p>
</div>
##### 知识库的建立方式有两种：
1. 上传本地的文本文件，目前只支持*.txt 文件格式；
2. 通过wikipedia的API接口获得指定词条的内容，用户可以输入词条的名称，程序会通过API接口爬取词条内容，然后存储为本地文本文件（大陆境内需要有扶墙环境）
##### 文本文件的分割处理：
由于GPT的embedding接口有tokens 限制，所以需要将文本切割成符合处理要求的大小，进而形成一个文档数组
##### 向量数据库的选择：
可以用作AI使用的Vectorstore 有很多选择，Chroma比较轻量，部署也相对容易，将处理后的文档插入ChromaDB后，就可以作为后续AI本地知识库问答的数据源了
##### AI问答：
Azure Open AI提供非常简洁的API调用，可以比较轻松的实现API接口的AI问答，针对本地知识库的问答核心就是先基于用户问题在Vectorstore中找到相关的文本内容，这部分内容将作为AI回答用户问题的提示内容，再将文本内容和用户问题一起加入提示词模板（Promot Template）就可以发给Open AI 获得自己希望的答案了。
##### 语音问答：
只是简单的调用了Azure的Cognitive Services （https://learn.microsoft.com/zh-cn/azure/cognitive-services/speech-service/ ）本质上还是基于文本内容的问答，语音问答在部分场景可以解决输入的问，更贴近一些真实的AI 使用场景
##### 其他：
程序只是自己在学习过程中写的一个简单的demo，有很多不足的地方，后续有时间也会考虑进一步完善
