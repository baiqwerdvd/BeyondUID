from gsuid_core.utils.download_resource.download_core import download_all_file

from BeyondUID.utils.resource.RESOURCE_PATH import charremoteicon700_path, itemiconbig_path


async def download_all_file_from_cos():
    await download_all_file(
        "BeyondUID",
        {
            "resource/charremoteicon700": charremoteicon700_path,
            "resource/itemiconbig": itemiconbig_path,
        },
    )
