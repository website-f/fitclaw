RECIPEPREFIX := >
COMPOSE := docker compose

up:
>$(COMPOSE) up -d --build

down:
>$(COMPOSE) down

restart:
>$(COMPOSE) restart

logs:
>$(COMPOSE) logs -f --tail=200

ps:
>$(COMPOSE) ps

shell:
>$(COMPOSE) exec api /bin/bash

bot-shell:
>$(COMPOSE) exec bot /bin/bash

worker-shell:
>$(COMPOSE) exec worker /bin/bash

