"""Resolve CLI binaries the way a shell would, for subprocess.run(shell=False).

Windows ships gcloud/gh as .cmd/.exe shims; subprocess.run with a plain list
of args won't find "gcloud" the way an interactive shell does.
"""

import shutil


def resolve(binary):
    return shutil.which(binary) or binary
