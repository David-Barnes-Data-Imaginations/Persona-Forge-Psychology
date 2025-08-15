### Now E2B has been ditched for Docker, in terminal run:

```
cd Docker
```
Workflow:

For Testing (Fresh Runs):
- Use docker-compose.test.yml (without volumes for testing)
  `docker-compose -f docker-compose.test.yml up --build`
  For Build Runs:
- Use docker-compose.yml (with volumes for development)
  `docker-compose -f docker-compose.yml up --build`

Then to stop run:
`docker-compose down`
Regardless of which used.

**Docker will then boot up the env in this order:**
1. Docker builds the image with all dependencies
2. Containers start (the app + Ollama server)
3. main.py runs automatically inside the container
4. Gradio UI becomes available at http://localhost:7860

You should see the usual blurb:

persona-forge | 📚 Setting up metadata embeddings...
persona-forge | 🛠️ Creating tools...
persona-forge | 🌐 Initializing Gradio interface...
persona-forge | ✅ Application startup complete!
persona-forge | Running on local URL: http://0.0.0.0:7860

💡 PyCharm Usage:

- Don't run main.py from PyCharm when using Docker like with the old E2B, I've removed the red herrings now also.
- Use PyCharm for editing code files
- Docker handles execution - go to the usual http://localhost:7860 in browser 
- In linux I tend to use firefox for all docker stuff as Google Chromne can be funny)

To stop it running (in terminal):

`docker-compose down`

⚡ Development Workflow:

1. Edit code in PyCharm
2. Run docker-compose up --build to test changes
3. Access the app at http://localhost:7860

The container automatically mounts your the agent and local code env, persistently.


🧪 For Testing Fresh Runs:

In Docker/docker-compose.test.yml, I've commented out these lines (to remove persistency for testing fresh runs):

```
# volumes:
#   - ../:/app
#   - ../src/data:/app/data
```

- It still isolates containered environment - From your local changes
- It Verifies all files are properly copied - During Docker build
---
