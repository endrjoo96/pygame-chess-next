class Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        """Zwraca jedyną instancję klasy, tworząc ją przy pierwszym wywołaniu."""
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]