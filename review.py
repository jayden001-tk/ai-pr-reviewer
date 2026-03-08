import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def review_code(diff):

    prompt = f"""
You are a senior software engineer.

Review the following pull request diff and identify:

- bugs
- security issues
- performance problems
- improvements

Diff:
{diff}
"""

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )

    print(response.output_text)
    
