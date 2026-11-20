"""Typed errors for explicit file-explorer operations."""

from __future__ import annotations


class FileOperationError(RuntimeError):
    """Base error for a rejected or failed file operation."""

    status = 400


class InvalidPath(FileOperationError):
    status = 400


class InvalidName(FileOperationError):
    status = 400


class ConfirmationRequired(FileOperationError):
    status = 400


class RecursiveDeleteRequired(FileOperationError):
    status = 400


class PathDenied(FileOperationError):
    status = 403


class RootDenied(FileOperationError):
    status = 403


class FileMissing(FileOperationError):
    status = 404


class FileConflict(FileOperationError):
    status = 409


class DeviceBusy(FileOperationError):
    status = 409


class FilesUnavailable(FileOperationError):
    status = 503
