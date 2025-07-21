# 🤖 OpenAI Agents Redis

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Redis](https://img.shields.io/badge/redis-%23DD0031.svg?style=flat&logo=redis&logoColor=white)](https://redis.io/)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT-green.svg)](https://openai.com/)

> Native [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) session management implementation using [Redis](https://redis.io) as the persistence layer.


## Demo

<p align="center">
    <a href="https://www.youtube.com/watch?v=DWr_Ata4gxQ">
        <img src="https://img.youtube.com/vi/DWr_Ata4gxQ/0.jpg" alt="Demo Video" width="560" />
    </a>
</p>

## ✨ Features

- 🧠 **Intelligent Agents**: Built on OpenAI's powerful Agents SDK
- ⚡ **Redis Integration**: Lightning-fast caching and persistent storage
- 🔄 **Conversation Memory**: Maintain context across interactions

## 🚀 Quick Start

### Installation

```bash
# Using uv (recommended)
uv add openai-agents-redis

# Using pip
pip install openai-agents-redis
```

### Basic Usage

```python
from agents_redis.session import RedisSession

session = RedisSession(
    session_id=session_id, #Use your own logic to generate a session_id
    redis_url="redis://localhost:6379",
)

# Your code for defining an Agent
# ...

# Starting the runner passing the session

result = Runner.run_streamed(
    starting_agent=current_agent, input=agent_input, context=current_context, session=session
)

```

## Development

### Testing Requirements

🐳 [Docker](https://www.docker.com/) <br>
⚡️ [uv](https://astral.sh/uv) <br>
🦾 [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) (optional) <br>
🔑 OpenAI API Key (optional) <br>

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov
```

## 📋 Roadmap

- [ ] Storing conversation context
- [ ] Full text search
- [ ] Vector similarity search & Hybrid Search
- [ ] Built-in monitoring dashboard

---

<p align="center">
  Made with ❤️ by <a href="https://github.com/rafaelpierre">Rafael</a>
</p>

<p align="center">
  ⭐ Star us on GitHub!
</p>