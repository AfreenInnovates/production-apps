# MediNotes Pro - Healthcare Consultation Assistant

A full-stack application that uses AI to generate consultation summaries, a short follow up email and patient communications from healthcare consultation notes (inputted by doctor). Built with Next.js (React), FastAPI (Python), and deployed on AWS App Runner.

**Live Demo:** https://xdiqkbih72.us-east-1.awsapprunner.com/

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Project Structure](#project-structure)
3. [Docker Setup Explained](#docker-setup-explained)
4. [API Routes Documentation](#api-routes-documentation)
5. [Why Docker for AWS?](#why-docker-for-aws)
6. [AWS App Runner Deployment Guide](#aws-app-runner-deployment-guide)
7. [Local Development](#local-development)
8. [Environment Variables](#environment-variables)
9. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

### Frontend (Next.js)

The frontend is built with Next.js 16 and React 19. It uses Tailwind CSS for styling and Clerk for authentication. The key aspect is that it's configured with `output: 'export'` in `next.config.ts`, which means when you build it, Next.js generates static HTML, CSS, and JavaScript files instead of requiring a Node.js server to run. These static files can be served by any web server, including our FastAPI backend.

The frontend code lives in the `/pages` directory, styles in `/styles`, and static assets like images in `/public`.

### Backend (FastAPI)

The backend is a Python FastAPI application that handles API requests. It integrates with OpenAI's GPT-4o-mini model to generate AI summaries. It also handles authentication by verifying JWT tokens from Clerk using the `fastapi-clerk-auth` library.

The backend uses Server-Sent Events (SSE) to stream responses back to the frontend in real-time. This creates a better user experience where the AI response appears to "type out" rather than waiting for the entire response.

### Deployment Strategy

Both frontend and backend are packaged into a single Docker container. FastAPI serves both the API endpoints AND the static Next.js files. This works because:

1. Next.js is built into static files (no server-side rendering needed)
2. FastAPI can serve static files just like nginx or Apache can
3. A single container is simpler to deploy and cheaper to run
4. Everything runs on port 8000 - FastAPI handles routing to either API endpoints or static files

---

## Project Structure

The project has a clear separation between frontend and backend:

- **`/api`** - Contains the FastAPI backend code (`index.py`) and Python dependencies (`requirements.txt`)
- **`/pages`** - Contains Next.js pages (React components)
  - `index.tsx` - The homepage/landing page
  - `product.tsx` - The consultation form page (requires subscription to access)
  - `_app.tsx` - Wraps the entire app with Clerk authentication provider
  - `_document.tsx` - Custom HTML document structure
- **`/styles`** - Contains global CSS styles
- **`/public`** - Contains static assets (images, favicon, etc.)
- **`Dockerfile`** - Defines how to build the container
- **`.dockerignore`** - Lists files to exclude from Docker build
- **`next.config.ts`** - Next.js configuration (sets static export mode)

---

## 🐳Docker Setup Explained

### Why Multi-Stage Build?

The Dockerfile uses a **multi-stage build** which means it has two separate build phases:

1. **Stage 1 (Frontend Builder):** Uses Node.js to build the Next.js app into static files
2. **Stage 2 (Runtime):** Uses Python to run FastAPI and serve those static files

This approach dramatically reduces the final image size because:
- The final image doesn't include Node.js (only needed for building)
- The final image doesn't include npm or build tools
- Only the compiled output and runtime dependencies are included

### Stage 1: Building the Frontend

The first stage starts with a Node.js image, copies the project files, installs dependencies, and runs the Next.js build. The build process:
- Compiles React components into JavaScript
- Processes CSS with Tailwind
- Bundles everything into optimized files
- Outputs everything to `/app/out` directory

The Clerk publishable key is passed as a build argument so it gets baked into the JavaScript bundles at build time. This is necessary because Next.js needs to know the Clerk configuration when it builds the app.

### Stage 2: Running the Backend

The second stage starts fresh with a Python image. It:
- Installs Python dependencies (FastAPI, OpenAI SDK, Clerk auth library, etc.)
- Copies the FastAPI code from `/api`
- **Crucially:** Copies the built Next.js files from Stage 1's `/app/out` to `/app/static`

This is the magic that allows FastAPI to serve the frontend - it has all the static HTML/CSS/JS files in the `/app/static` directory.

### Health Check

The Dockerfile includes a healthcheck that pings the `/health` endpoint every 30 seconds. This tells Docker (and AWS App Runner) whether the container is running correctly. If the health check fails, the orchestration system knows to restart the container.

### Port and Server

The container exposes port 8000 and starts uvicorn (the ASGI server that runs FastAPI). The server listens on `0.0.0.0` which means it accepts connections from any network interface - this is required for containers because they might receive traffic from various sources.

---

## API Routes

### Why FastAPI Serves Both API and Frontend?

This is a key architectural decision. When Next.js is built with static export, it creates regular HTML/CSS/JS files - just like a traditional website. These files don't need a Node.js server to run. FastAPI can serve these static files just like any web server (nginx, Apache, etc.) while also handling API requests.

This approach works because:
- Next.js static export creates plain files (no server-side logic)
- FastAPI has built-in static file serving capabilities
- A single container is simpler to manage than separate frontend/backend containers
- Cost-effective: one container instead of two

### Route: `GET /health`

**Purpose:** Health check endpoint for monitoring and orchestration.

**Why it's critical:**
- AWS App Runner pings this endpoint to verify the service is running
- Docker's healthcheck uses this (configured in Dockerfile)
- Load balancers use it to route traffic only to healthy instances
- Monitoring systems can check application status

**What it does:** Returns a simple JSON response indicating the service is healthy. This endpoint should always work and be fast - it doesn't do any heavy processing.

**When it's called:** 
- Every 30 seconds by Docker healthcheck
- Periodically by AWS App Runner
- By monitoring/alerting systems
- By load balancers before routing traffic

---

### Route: `OPTIONS /api`

**Purpose:** Handles CORS (Cross-Origin Resource Sharing) preflight requests.

**Why needed:** When a browser makes a request to a different domain than the one serving the page, it first sends an OPTIONS request to check if the cross-origin request is allowed. This is called a "preflight" request.

Even though our frontend and backend are in the same container, some deployments might serve them from different origins (different domains or subdomains). The OPTIONS endpoint ensures the browser knows it's safe to make the actual POST request.

**When it's called:** Automatically by the browser before POST requests if the request is going to a different origin than the current page.

---

### Route: `POST /api`

**Purpose:** The main API endpoint that generates consultation summaries using AI.

**Authentication:** Requires a valid Clerk JWT token in the `Authorization` header. The token is verified against Clerk's JWKS (JSON Web Key Set) endpoint before processing the request.

**What it does:**
1. Validates the JWT token with Clerk
2. Extracts user information from the token
3. Takes the consultation data (patient name, date, notes)
4. Calls OpenAI's GPT-4o-mini model with a carefully crafted prompt
5. Streams the response back using Server-Sent Events (SSE)

**Why SSE instead of regular JSON?**
- AI responses can be very long (several paragraphs)
- Streaming shows progress immediately (typing effect)
- Better user experience - feels much faster
- Users see content appearing in real-time instead of waiting for the full response

**How streaming works:** The OpenAI API returns chunks of text as they're generated. FastAPI immediately forwards each chunk to the client. The frontend receives these chunks and displays them as they arrive, creating a real-time typing effect.

**Error Handling:**
- Missing or invalid JWT → Returns authentication error immediately
- OpenAI API errors → Closes the stream and returns error
- Network issues → Frontend detects stream closure and shows error message

---

### Route: `GET /`

**Purpose:** Serves the Next.js homepage (`index.html`).

**How it works:** FastAPI checks if `/app/static/index.html` exists and serves it. The browser receives the HTML, which includes links to JavaScript and CSS files. The browser then loads those assets, and React takes over to handle client-side routing and interactivity.

**Why serve through FastAPI instead of directly?**
- FastAPI handles routing logic - it can decide whether to serve a static file or handle an API request
- Single entry point for all requests simplifies deployment
- Can add middleware like authentication, logging, rate limiting
- Consistent error handling

---

### Route: `GET /{full_path:path}` (Catch-all)

**Purpose:** Serves all other Next.js routes and handles client-side routing.

**How it works:**
1. First checks if the path matches an actual file (like `favicon.ico`) → serves it directly
2. Checks if the path is a directory with an `index.html` → serves that file
3. Otherwise → serves the root `index.html` and lets React Router handle the routing client-side

**Why this pattern?**
- Next.js static export creates HTML files for some routes but not all
- Client-side routing means React handles navigation after the initial page load
- The catch-all ensures all routes work, even if Next.js didn't generate a specific HTML file for that route
- Static files (images, etc.) are served directly for performance

**Examples:**
- `/product` → Serves `index.html`, React Router shows the product page
- `/favicon.ico` → Serves the favicon file directly
- `/api` → Returns 404 (prevents catch-all from interfering with API routes)

---

### Route: `GET /_next/*`

**Purpose:** Serves Next.js build assets (JavaScript bundles, CSS files, images referenced by Next.js).

**How it works:** FastAPI mounts the `/app/static/_next` directory to the `/_next` URL path. Any request to `/_next/...` automatically serves files from that directory.

**What's in `/_next`?**
- JavaScript chunks - Next.js splits code into smaller chunks for faster loading
- CSS files - Compiled Tailwind CSS and component styles
- Static assets - Images and files referenced in the Next.js code
- Source maps - For debugging (in development builds)

These assets are automatically generated by Next.js during the build process and are essential for the frontend to function.

---

## Why Docker for AWS?

Docker solves several deployment challenges:

**Containerization:** Packages everything together (frontend, backend, dependencies) into one portable unit. This means the application runs the same way on your local machine, in testing, and in production.

**Reproducibility:** The Docker image is immutable - once built, it contains exactly what's needed to run. No "works on my machine" problems because everyone uses the same image.

**Isolation:** The container has its own file system and dependencies. No conflicts with other applications or system libraries.

**Easy Deployment:** Build once, push to a container registry (like AWS ECR), and deploy anywhere. AWS App Runner can pull the image and run it without needing to configure servers, install dependencies, or manage updates.

**Scalability:** Container orchestration platforms can easily spin up multiple instances when traffic increases and scale down when it decreases.

**Cost-Effective:** Pay only for the compute resources you actually use. With auto-scaling, you're not paying for idle servers.

Docker is ideal for AWS App Runner because App Runner is designed to run containers. It handles all the infrastructure management - you just provide the container image and App Runner takes care of the rest.

---

## AWS App Runner Deployment Guide

### Prerequisites

You'll need:
- An AWS account (sign up at aws.amazon.com)
- AWS CLI installed and configured on your computer
- Docker installed (for building and testing locally)
- Your code pushed to a Git repository (GitHub, GitLab, or Bitbucket)

### Step 1: AWS Account Setup

When you first create an AWS account, you get a "root user" - this is the main account with full access. **Important:** Only use the root user for initial setup tasks like creating IAM users and managing billing. Never use root credentials for daily operations.

The root user credentials are the email and password you used to sign up for AWS.

### Step 2: Create IAM User

IAM (Identity and Access Management) users are separate accounts with specific permissions. You should create an IAM user for deploying your application instead of using root credentials.

**Why use IAM users?**
- **Security:** If credentials are compromised, the damage is limited to what that user can do
- **Audit trail:** AWS logs show which IAM user performed each action
- **Permissions:** You can grant only the minimum permissions needed (principle of least privilege)
- **Best practice:** Industry standard to avoid using root credentials

**Steps to create IAM user:**
1. Go to AWS Console → IAM → Users → Add Users
2. Choose a username (e.g., `app-runner-deploy`)
3. Select access type:
   - **Programmatic access** - Required for CLI/API usage (for pushing Docker images)
   - **AWS Management Console access** - Optional, for logging into AWS Console
4. Attach policies:
   - `AmazonEC2ContainerRegistryFullAccess` - Allows pushing/pulling Docker images
   - `AWSAppRunnerFullAccess` - Allows creating and managing App Runner services
5. **Save the credentials immediately:**
   - Access Key ID
   - Secret Access Key
   - Download the CSV file - you won't be able to see the secret key again!

6. Configure AWS CLI with these credentials so you can push Docker images from your computer.

### Step 3: Create ECR Repository

ECR (Elastic Container Registry) is AWS's Docker image storage service. Think of it like Docker Hub, but private and integrated with AWS.

You need to create a repository where your Docker images will be stored. App Runner will pull images from this repository to deploy your application.

The repository name can be anything (e.g., `medinotes-pro`). After creating it, note the repository URI - it looks like `<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/<REPO_NAME>`.

### Step 4: Build and Push Docker Image

Build your Docker image locally using the Dockerfile. Make sure to pass the Clerk publishable key as a build argument so it gets baked into the Next.js build.

Tag the image with the ECR repository URI, then authenticate Docker with ECR and push the image. The push uploads your image to ECR where App Runner can access it.

After pushing, your image is available in ECR with a specific tag (usually `latest`).

### Step 5: Create App Runner Service

App Runner service is where your application runs. You configure:
- **Source:** Point to your ECR image
- **Service settings:** CPU, memory, port (8000)
- **Auto-scaling:** Minimum and maximum instances, concurrency
- **Health check:** Path (`/health`), interval, timeouts
- **Environment variables:** Clerk keys, OpenAI key, JWKS URL

You can create the service through the AWS Console (easier, visual interface) or using AWS CLI (programmatic, good for automation).

Once created, App Runner:
1. Pulls your Docker image from ECR
2. Starts containers with your specified configuration
3. Begins health checks
4. Provides a URL where your application is accessible

### Step 6: Configure Auto-Deployment

You can set up automatic deployments so that whenever you push a new image to ECR, App Runner automatically deploys it. This is called "auto-deployment" and can be enabled in the service settings.

Alternatively, you can set up CI/CD with GitHub Actions that automatically builds and pushes images when you push code to your repository.

### Step 7: Verify Deployment

After the service is created, App Runner shows a URL where your application is accessible. The first deployment takes a few minutes as App Runner:
- Pulls the image from ECR
- Starts containers
- Runs health checks
- Configures load balancing

Once the service status shows "Running" and health checks pass, your application is live!

---

## Local Development

### Prerequisites

Make sure you have:
- Node.js 18 or higher installed
- Python 3.12 or higher installed
- Docker installed (optional, for testing the containerized setup)

### Running Locally (Development Mode)

You can run the frontend and backend separately during development:

**Terminal 1 - Frontend:**
Install dependencies and start the Next.js development server. This runs on port 3000 with hot-reloading (changes appear instantly without restarting).

**Terminal 2 - Backend:**
Navigate to the API directory, install Python dependencies, and start FastAPI with uvicorn in reload mode. This runs on port 8000 and automatically restarts when you change code.

During development, the frontend makes API calls to `http://localhost:8000/api` (you might need to configure this in the frontend code).

### Running with Docker (Production-like)

You can also test the production setup locally by building and running the Docker container. This ensures your application works the same way locally as it will in production.

Build the image with the build argument for Clerk publishable key, then run it with environment variables for Clerk secret key, JWKS URL, and OpenAI API key. The application will be accessible at `http://localhost:8000`.

---

## Environment Variables

### Frontend (Build Time)

The frontend needs the Clerk publishable key at build time. This gets baked into the JavaScript bundles so the browser can connect to Clerk for authentication.

The variable name must start with `NEXT_PUBLIC_` - this tells Next.js to make it available in the browser. Without this prefix, the variable is only available on the server.

### Backend (Runtime)

The backend needs three environment variables at runtime:

**CLERK_SECRET_KEY:** Used to verify JWT tokens. This is private and should never be exposed to the browser.

**CLERK_JWKS_URL:** The endpoint where Clerk publishes public keys for JWT verification. The backend fetches these keys to verify tokens are valid and signed by Clerk.

**OPENAI_API_KEY:** Your OpenAI API key for making requests to GPT-4o-mini. This is used to generate the consultation summaries.

**NEXT_PUBLIC_API_URL:** Optional. Only needed if you want the frontend to call an API on a different domain. In our single-container setup, this isn't needed because the frontend uses relative paths (`/api`).

### How to Get Clerk Keys

1. Go to clerk.com and sign in to your dashboard
2. Select your application
3. Navigate to API Keys section
4. Copy the Publishable Key (starts with `pk_`) for frontend
5. Copy the Secret Key (starts with `sk_`) for backend
6. Find the JWKS URL in the same section (format: `https://<instance>.clerk.accounts.dev/.well-known/jwks.json`)

### How to Get OpenAI Key

1. Go to platform.openai.com and sign in
2. Navigate to API Keys section
3. Create a new secret key
4. Copy it immediately - it's only shown once!

---

## Troubleshooting

### Health Check Failing

**Symptoms:** Container keeps restarting, service shows as unhealthy.

**Causes:**
- The `/health` route doesn't exist or returns an error
- Port 8000 isn't exposed correctly
- Application isn't starting properly

**Solutions:**
- Verify the `/health` endpoint exists in `api/index.py` and returns a 200 status
- Check App Runner logs to see startup errors
- Ensure the Dockerfile exposes port 8000
- Verify the CMD in Dockerfile starts uvicorn correctly

### Static Files Not Loading

**Symptoms:** Page loads but is blank, CSS missing, JavaScript errors in console.

**Causes:**
- Next.js build didn't complete successfully
- Files weren't copied to `/app/static` in Docker
- FastAPI isn't mounting the `/_next` directory correctly

**Solutions:**
- Verify `npm run build` creates the `/out` directory with files
- Check Dockerfile copies `/app/out` to `/app/static` in Stage 2
- Verify FastAPI code mounts `/_next` directory if it exists
- Check browser console for 404 errors on specific files
- Ensure build process completes without errors

### CORS Errors

**Symptoms:** Browser console shows "CORS policy" errors, API requests fail.

**Causes:**
- CORS middleware not configured correctly
- OPTIONS endpoint missing or not working
- Frontend and backend on different origins

**Solutions:**
- Verify CORS middleware is added to FastAPI app
- Check `allow_origins` includes your frontend domain (or `["*"]` for testing)
- Ensure OPTIONS endpoint exists for `/api`
- Verify CORS headers are included in responses

### Authentication Failing

**Symptoms:** "Authentication required" error, 401 Unauthorized responses.

**Causes:**
- Invalid or missing JWT token
- Incorrect Clerk JWKS URL
- Token expired or revoked
- Wrong Clerk environment (test vs production)

**Solutions:**
- Verify `CLERK_JWKS_URL` matches your Clerk instance
- Check Clerk keys are for production (not test) if deploying to production
- Verify JWT token is being sent in `Authorization: Bearer <token>` header
- Check Clerk dashboard to ensure API keys are active
- Verify token format and expiration

### OpenAI API Errors

**Symptoms:** Streaming fails, errors in console, no AI response.

**Causes:**
- Invalid or missing OpenAI API key
- Insufficient credits/quota
- Rate limit exceeded
- Model name incorrect

**Solutions:**
- Verify `OPENAI_API_KEY` is set correctly
- Check OpenAI dashboard for account credits and usage
- Verify model name (`gpt-4o-mini`) is correct and available
- Check rate limits in OpenAI dashboard
- Ensure API key has proper permissions

### App Runner Deployment Fails

**Symptoms:** Service creation fails, deployment errors, service won't start.

**Causes:**
- ECR repository doesn't exist or image not pushed
- IAM permissions insufficient
- Health check failing
- Environment variables missing or incorrect
- Image build errors

**Solutions:**
- Verify ECR repository exists and contains your image
- Check IAM user has `AmazonEC2ContainerRegistryReadOnlyAccess` and `AWSAppRunnerFullAccess`
- Verify health check path (`/health`) matches your route
- Check all required environment variables are set
- Review App Runner service logs for specific error messages
- Test Docker image locally first to catch build issues
