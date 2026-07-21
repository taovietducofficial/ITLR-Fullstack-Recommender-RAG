from dagster import file_relative_path, Definitions
from dagstermill import define_dagstermill_asset, ConfigurableLocalOutputNotebookIOManager
analysis_jupyter_notebook = define_dagstermill_asset(
    name="analysis_jupyter_notebook",
    notebook_path=file_relative_path(__file__, "..//notebooks//iris-kmeans.ipynb"),
    group_name="Notebooks",
    io_manager_key="output_notebook_io_manager",
)


defs = Definitions(
    assets=[analysis_jupyter_notebook],
    resources={"output_notebook_io_manager": ConfigurableLocalOutputNotebookIOManager()}
)