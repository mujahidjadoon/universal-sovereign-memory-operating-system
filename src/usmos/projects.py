from src.memory import memory_engine


def project_create(name, description=""):

    return memory_engine.create_project(
        name=name,
        description=description
    )


def project_use(name):

    return memory_engine.set_current_project(name)


def project_current():

    return memory_engine.get_current_project()
