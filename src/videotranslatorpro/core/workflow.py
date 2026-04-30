from dataclasses import dataclass


@dataclass
class WorkflowState:
    input_video: str = ""
    output_dir: str = ""


class VideoTranslationWorkflow:
    """Phase 1 placeholder workflow.

    This class will orchestrate extraction, ASR, translation, subtitles,
    dubbing, and rendering in later phases.
    """

    def __init__(self) -> None:
        self.state = WorkflowState()

    def run(self) -> None:
        """Placeholder entrypoint for future pipeline execution."""
        return None
