from django.core.files.storage import FileSystemStorage


class FileSystemOverwriteStorage(FileSystemStorage):
    """
    Custom file system storage: Overwrite get_available_name to make Django replace files instead of
    creating new ones over and over again.
    https://gist.github.com/fabiomontefuscolo/1584462
    """

    def get_available_name(self, name, max_length=None):
        try:
            self.delete(name)
        except PermissionError:
            ...
        return super().get_available_name(name, max_length)
