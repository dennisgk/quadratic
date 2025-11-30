# TODO

1. I edited a new .env file in
2. I rename the docker-compose.yml to docker-compose.old.yml and copy it to docker-compose.yml
3. I update the docker-compose.yml and remove a lot of services
4. I run the command 
CLIENT_DEV=false docker compose --profile all --env-file .env up -d

5. then maybe run
docker compose down
docker compose pull

pull is maybe optional
then maybe run the 4 command with --build but not sure if necessary
down might not even be necessary