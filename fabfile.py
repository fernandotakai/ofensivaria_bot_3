from fabric.api import local, env
from dockerfabric.api import docker_fabric


env.docker_tunnel_local_port = 22024  # or any other available port above 1024 of your choice

docker_client = docker_fabric()


def get_image_name():
    image_name = 'ofensivaria-bot-3'

    if env.docker_username:
        image_name = '%s/%s' % (env.docker_username, image_name)

    return image_name


def poll():
    local('docker-compose run --name bot --service-ports --rm poll')


def web():
    local('docker-compose run --name bot --service-ports --rm app')


def build():
    local('docker build . -t %s' % get_image_name())


def push():
    if getattr(env, 'docker_username', None):
        local('docker push %(docker_username)s/ofensivaria-bot-3' % env)
    else:
        print('No docker_username set. Not pushing.')


def pull():
    docker_client.pull(get_image_name())


def stop():
    docker_client.stop('ofensivaria')


def logs():
    docker_client.logs('ofensivaria')


def start():
    docker_client.start('ofensivaria')


def remove():
    docker_client.remove_container('ofensivaria')


def start_from_scratch():
    docker_env = {
        'TOKEN': env.telegram_token,
        'REDIS_HOST': 'redis',
        'REDIS_PORT': '6379',
        'DEBUG': ''
    }


    config = docker_client.create_host_config(
        port_bindings={8000: 8000},
        links={'redis': 'redis'},
        binds=['/markov:/markov']
    )


    docker_client.create_container(get_image_name(), environment=docker_env,
                                   name='ofensivaria', host_config=config, detach=True)


def start_redis():
    status = get_container_status('redis')

    if status == 'deleted':
        config = docker_client.create_host_config(binds=['/data:/data'])

        docker_client.create_container('redis', command='--appendonly yes', host_config=config,
                                       name='redis', detach=True)

    docker_client.start('redis')


STEPS = {
    'running': (build, push, stop, remove, pull, start_redis, start_from_scratch, start),
    'exited': (build, push, remove, pull, start_redis, start_from_scratch, start),
    'deleted': (build, push, pull, start_redis, start_from_scratch, start),
    'created': (build, push, pull, start_redis, start_from_scratch, start)
}


def deploy():
    status = get_container_status('ofensivaria')

    for step in STEPS[status]:
        step()


def get_container_status(container_name):
    try:
        container = docker_client.containers(filters={'name': container_name}, all=True)[0]
        return container['State']
    except IndexError:
        return 'deleted'
