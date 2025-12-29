TextRoute

TextRoute is an experimental, community-focused project that explores how AI can reduce noise in group messaging by routing messages only to the people most likely to be relevant—without changing how people communicate.

Users interact entirely through plain text messages.
No apps, no accounts, no special commands.

The goal is to improve clarity and cooperation in group communication while keeping humans in control and communities inclusive.


What This Repository Contains

This repository is organized as a monorepo with a clear separation between:

The core TextRoute application
Supporting tools, infrastructure, and documentation

Detailed implementation notes live in the README files inside each subproject.


High-Level Capabilities

At a conceptual level, TextRoute explores:
Intent-aware message routing
Context-aware relevance filtering
Human-in-the-loop decision support
Text-only workflows for maximum accessibility

Typical message categories include:
Requests for help or services
Offers of help or resources
Announcements
Questions and coordination messages


Repository Structure
.
├── textroute/              # Core FastAPI application (main product)
│   ├── app/                # API and application logic
│   ├── domain/             # Domain models and business rules
│   ├── schemas/            # Pydantic schemas
│   ├── db/                 # Database logic and migrations
│   ├── prompts/            # LLM prompts and templates
│   ├── Dockerfile
│   └── README.md           # Detailed app-level documentation
│
├── docs/mkdocs/            # Project documentation site (MkDocs)
│   ├── docs/
│   ├── mkdocs.yml
│   └── Dockerfile
│
├── infra/                  # Infrastructure and deployment assets
│   ├── nginx/              # Reverse proxy configuration
│   ├── pg/                 # PostgreSQL configuration
│   └── docker-compose.yml
│
├── tools/                  # Development and testing tools
│   ├── sms-simulator/      # SMS provider simulator (non-production)
│   └── postman/            # API collections
│
├── scripts/                # Automation and helper scripts
│   └── build-image.sh
│
└── README.md               # This file (high-level overview)


Tools Included

This repository includes several supporting tools to aid development and testing:
SMS Simulator
A local tool for simulating SMS providers when testing TextRoute.
Not intended for production use.
Postman Collections
Predefined API requests for manual testing and exploration.
MkDocs Documentation Site
A structured documentation site for guides, concepts, and architecture notes.
Shell Scripts
Small automation helpers for building images and managing local workflows.


Philosophy
TextRoute is designed to assist communities, not control them.
Key principles:
Respect people’s attention
Preserve transparency
Keep humans involved in sensitive decisions
Favor clarity over automation for its own sake
This is a learning-oriented, experimentation-friendly project focused on responsible AI usage.


Where to Go Next
📄 TextRoute application details: textroute/README.md
📚 Documentation site: docs/mkdocs/
🧪 Testing tools: tools/sms-simulator/