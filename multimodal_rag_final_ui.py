
import streamlit as st
from datasets import load_dataset
import os
from PIL import Image
import warnings
from matplotlib import pyplot as plt
import base64
from dotenv import load_dotenv
import chromadb
from chromadb.utils.embedding_functions import OpenCLIPEmbeddingFunction
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from chromadb.utils.data_loaders import ImageLoader
from matplotlib import pyplot as plt

# Suppress warnings
warnings.filterwarnings("ignore")
load_dotenv()

# === Load the flower dataset ===
st.title("Flower Arrangement Query and Image Retrieval Service")


# Load dataset from Hugging Face
@st.cache_data
def load_flower_dataset():
    return load_dataset("huggan/flowers-102-categories")


ds = load_flower_dataset()

# === Define ChromaDB for image search ===
chroma_client = chromadb.PersistentClient(path="./data/flower.db")
image_loader = ImageLoader()
embedding_function = OpenCLIPEmbeddingFunction()
flower_collection = chroma_client.get_or_create_collection(
    "flowers_collection",
    embedding_function=embedding_function,
    data_loader=image_loader,
)


# === Helper function to display images ===
def show_image_from_uri(uri, width=200):
    img = Image.open(uri)
    st.image(img, width=width)


# === Helper function to format inputs for the prompt ===
def format_prompt_inputs(data, user_query):
    inputs = {}
    inputs["user_query"] = user_query

    # Get first two image paths
    image_path_1 = data["uris"][0][0]
    image_path_2 = data["uris"][0][1]

    # Encode images to base64
    with open(image_path_1, "rb") as image_file:
        image_data_1 = image_file.read()
    inputs["image_data_1"] = base64.b64encode(image_data_1).decode("utf-8")

    with open(image_path_2, "rb") as image_file:
        image_data_2 = image_file.read()
    inputs["image_data_2"] = base64.b64encode(image_data_2).decode("utf-8")

    return inputs


# === Query the VectorDB (ChromaDB) for images based on text query ===
def query_db(query, results=2):
    res = flower_collection.query(
        query_texts=[query], n_results=results, include=["uris", "distances"]
    )
    return res


# === Run LangChain Vision Model (GPT-4 with image support) ===
@st.cache_resource
def get_vision_model():
    return ChatOpenAI(model="gpt-4o", temperature=0.0)


# Vision model and parser
vision_model = get_vision_model()
parser = StrOutputParser()

# Multimodal input: text + images to generate bouquet suggestions
image_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a talented florist. Answer using the given image context with direct references to parts of the images provided. "
            "Use a conversational tone, and apply markdown formatting where necessary.",
        ),
        (
            "user",
            [
                {
                    "type": "text",  # Text query as one modality
                    "text": "what are some good ideas for a bouquet arrangement {user_query}",
                },
                {
                    "type": "image_url",  # First image as the second modality
                    "image_url": "data:image/jpeg;base64,{image_data_1}",
                },
                {
                    "type": "image_url",  # Second image as another modality
                    "image_url": "data:image/jpeg;base64,{image_data_2}",
                },
            ],
        ),
    ]
)

# === Define the LangChain Chain: Combines text and image data ===
vision_chain = image_prompt | vision_model | parser

# === Streamlit UI ===
# Input text for the query (text input as part of multimodal interaction)
query = st.text_input("Enter your query (e.g., 'pink flower with yellow center'):")

# Display input query
if query:
    st.write(f"Your query: {query}")

    # Retrieve images based on the text query (image retrieval based on text)
    with st.spinner("Retrieving images..."):
        results = query_db(query)

    # Display the retrieved images (image recommendation based on query)
    st.write("Here are some images based on your query:")
    for uri in results["uris"][0]:
        show_image_from_uri(uri)

    # Format prompt inputs for LLM (text + images for final recommendations)
    with st.spinner("Generating suggestions..."):
        prompt_input = format_prompt_inputs(results, query)
        response = vision_chain.invoke(prompt_input)

    # Show the response generated by the LLM (suggestions based on multimodal input)
    st.markdown(f"### Suggestions for bouquet arrangement:")
    st.write(response)
