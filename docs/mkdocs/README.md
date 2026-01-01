mkdocs-site/
├── Dockerfile
├── docker-compose.yml
├── mkdocs.yml
└── docs/
    ├── index.md
    ├── user-guide.md
    ├── philosophy.md
    └── about.md


5. Local Development (Live Reload)
docker compose up --build


Then open:

http://localhost:8000


✔ Edit Markdown
✔ Browser auto-refreshes
✔ No rebuild needed while writing

6. Production Build (Static Files)

When ready to deploy:

docker run --rm -v $(pwd):/app mkdocs-material build


This creates:

site/


You can now serve this with Nginx.