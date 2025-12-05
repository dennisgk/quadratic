# TODO

1. I edited a new .env file in
2. I rename the docker-compose.yml to docker-compose.old.yml and copy it to docker-compose.yml
3. I update the docker-compose.yml and remove a lot of services
4. I run the command - before this I had to fix a bunch of weird string | undefined typescript errors
CLIENT_DEV=false docker compose --profile all --env-file .env up -d

5. then maybe run
docker compose down
docker compose pull

pull is maybe optional
then maybe run the 4 command with --build but not sure if necessary
down might not even be necessary

6. Change the kratos config
7. edited the dockerfile in quadratic-client to transfer download-pyodide.sh and then run it in the container

docker compose build ...

also the custom patch has hardcoded quadratic.kountouris.org
the custom lib right now has quadraticapi.kountouris.org hardcoded in right now in the __init__
There are hard coded creds in pyodide.info.GET.ts