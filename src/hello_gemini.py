from google import genai

PROJECT = "project-24118c4c-2dff-4450-ad0"
LOCATION = "global"
MODEL = "gemini-3.5-flash"

client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)

resp = client.models.generate_content(
    model=MODEL,
    contents="In two sentences, explain what 'big blinds per hand' measures in poker.",
)
print(resp.text)
