import os
from fastapi import FastAPI, Depends, Request  # type: ignore
from fastapi.responses import StreamingResponse, FileResponse  # type: ignore
from fastapi.staticfiles import StaticFiles  # type: ignore
from fastapi.middleware.cors import CORSMiddleware  # type: ignore
from pydantic import BaseModel  # type: ignore
from fastapi_clerk_auth import ClerkConfig, ClerkHTTPBearer, HTTPAuthorizationCredentials  # type: ignore
from openai import OpenAI  # type: ignore

app = FastAPI()

# Serve static files (Next.js build output)
static_path = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.exists(static_path):
    # Mount _next directory if it exists (Next.js static assets)
    _next_path = os.path.join(static_path, "_next")
    if os.path.exists(_next_path) and os.path.isdir(_next_path):
        app.mount("/_next", StaticFiles(directory=_next_path), name="next")

# Add CORS middleware for AWS deployment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

clerk_config = ClerkConfig(jwks_url=os.getenv("CLERK_JWKS_URL"))
clerk_guard = ClerkHTTPBearer(clerk_config)


class Visit(BaseModel):
    patient_name: str
    date_of_visit: str
    notes: str


system_prompt = """
You are provided with notes written by a doctor from a patient's visit.
Your job is to summarize the visit for the doctor and provide an email.
Reply with exactly three sections with the headings:
### Summary of visit for the doctor's records
### Next steps for the doctor
### Draft of email to patient in patient-friendly language
"""


def user_prompt_for(visit: Visit) -> str:
    return f"""Create the summary, next steps and draft email for:
Patient Name: {visit.patient_name}
Date of Visit: {visit.date_of_visit}
Notes:
{visit.notes}"""


@app.get("/health")
async def health_check():
    """Health check endpoint for Docker and AWS"""
    return {"status": "healthy", "service": "consultation-api"}


@app.options("/api")
async def options_handler():
    """Handle preflight OPTIONS request for CORS"""
    return {"status": "ok"}


@app.post("/api")
def consultation_summary(
    visit: Visit,
    creds: HTTPAuthorizationCredentials = Depends(clerk_guard),
):
    user_id = creds.decoded["sub"]  # Available for tracking/auditing
    client = OpenAI()

    user_prompt = user_prompt_for(visit)

    prompt = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    stream = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=prompt,
        stream=True,
    )

    def event_stream():
        for chunk in stream:
            text = chunk.choices[0].delta.content
            if text:
                lines = text.split("\n")
                for line in lines[:-1]:
                    yield f"data: {line}\n\n"
                    yield "data:  \n"
                yield f"data: {lines[-1]}\n\n"

    response = StreamingResponse(event_stream(), media_type="text/event-stream")
    # Add CORS headers for AWS
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response


@app.get("/")
async def serve_root():
    """Serve Next.js app root"""
    static_path = os.path.join(os.path.dirname(__file__), "..", "static")
    index_path = os.path.join(static_path, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"error": "Next.js app not found. Make sure the build output is in /static"}


@app.get("/{full_path:path}")
async def serve_nextjs_app(full_path: str):
    """Serve Next.js app for all other routes (handles client-side routing)"""
    static_path = os.path.join(os.path.dirname(__file__), "..", "static")
    
    # Skip API and health routes
    if full_path.startswith("api") or full_path == "health":
        return {"error": "Not found"}
    
    # If path exists as a file (e.g., favicon.ico), serve it
    file_path = os.path.join(static_path, full_path)
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    
    # Check if it's a directory with index.html
    if os.path.isdir(file_path):
        index_in_dir = os.path.join(file_path, "index.html")
        if os.path.exists(index_in_dir):
            return FileResponse(index_in_dir)
    
    # For all other routes, serve root index.html (Next.js handles client-side routing)
    index_path = os.path.join(static_path, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    
    # Fallback
    return {"error": "Not found"}