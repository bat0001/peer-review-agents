"""Hydra-based configuration system with structured configs."""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List
import yaml
import json
from pathlib import Path
from hydra.core.config_store import ConfigStore
from omegaconf import MISSING, OmegaConf


@dataclass
class TrainingConfig:
    """Training configuration."""
    # Batch settings
    total_batch_size: int = 65536  # Total batch size in tokens
    per_device_batch_size: int = 8  # Samples per device
    sequence_length: int = 1024
    # gradient_accumulation_steps is now calculated automatically

    # Training length (priority: max_steps > training_tokens)
    max_steps: Optional[int] = None  # Explicit step count
    training_tokens: Optional[float] = None  # Token budget in billions (e.g., 10 = 10B)
    grad_clip: float = 1.0
    
    # Checkpointing
    save_interval: int = 100
    eval_interval: int = 250
    eval_tokens: int = 20 * 524288

    # Threshold training
    ema_start_steps: int = 0  # >=0: start applying cutoff EMA updates at step N
    threshold_warmup_steps: int = -1  # -1 = disabled, >=0 = switch to threshold at step N

    # Other
    compile_model: bool = True
    mixed_precision: bool = True
    seed: int = 42

    def validate_batch_settings(self, world_size: int = 1) -> int:
        """
        Validate batch settings and calculate gradient accumulation steps.
        
        Args:
            world_size: Number of GPUs/processes
            
        Returns:
            gradient_accumulation_steps
            
        Raises:
            ValueError: If batch settings are invalid
        """
        # Calculate tokens per device per step
        tokens_per_device_per_step = self.per_device_batch_size * self.sequence_length
        
        # Calculate total tokens per step across all devices
        tokens_per_step = tokens_per_device_per_step * world_size
        
        # Check if total_batch_size is divisible by tokens_per_step
        if self.total_batch_size % tokens_per_step != 0:
            raise ValueError(
                f"total_batch_size ({self.total_batch_size}) must be divisible by "
                f"tokens_per_step ({tokens_per_step} = {self.per_device_batch_size} * "
                f"{self.sequence_length} * {world_size})"
            )
        
        # Calculate gradient accumulation steps
        gradient_accumulation_steps = self.total_batch_size // tokens_per_step
        
        # Validate the result
        if gradient_accumulation_steps <= 0:
            raise ValueError(
                f"Invalid gradient_accumulation_steps: {gradient_accumulation_steps}. "
                f"total_batch_size ({self.total_batch_size}) is too small for "
                f"per_device_batch_size ({self.per_device_batch_size}) * "
                f"sequence_length ({self.sequence_length}) * world_size ({world_size})"
            )
        
        return gradient_accumulation_steps

    def calculate_max_steps(self) -> int:
        """
        Calculate max_steps from max_steps or training_tokens.

        Priority: max_steps > training_tokens

        Returns:
            Number of training steps.

        Raises:
            ValueError: If neither max_steps nor training_tokens is specified
        """
        if self.max_steps is not None and self.max_steps > 0:
            return self.max_steps
        elif self.training_tokens is not None and self.training_tokens > 0:
            tokens = int(self.training_tokens * 1e9)  # billions to actual
            return tokens // self.total_batch_size
        else:
            raise ValueError("Must specify max_steps or training_tokens")


@dataclass
class DataConfig:
    """Data configuration."""
    data_path: str = "${oc.env:NANOCHAT_BASE_DIR}/base_data"
    tokenizer_type: str = "rustbpe"
    tokenizer_dir: str = "${oc.env:NANOCHAT_BASE_DIR}/tokenizer"
    tokenizer_threads: int = 4
    tokenizer_batch_size: int = 128
    nanochat_base_dir: str = "${oc.env:NANOCHAT_BASE_DIR}"
    num_workers: int = 4


@dataclass
class LoggingConfig:
    """Logging configuration."""
    use_wandb: bool = True
    wandb_project: str = "gpt2-refactored"
    wandb_entity: Optional[str] = None
    
    log_interval: int = 10
    log_metrics: List[str] = field(default_factory=lambda: [
        "loss", "learning_rate", "throughput"
    ])


@dataclass
class EvalConfig:
    """Evaluation configuration."""
    core_metric_every: int = 2000
    core_metric_max_per_task: int = 500
    core_eval_examples_per_forward: int = 1
    core_bundle_url: str = "https://karpathy-public.s3.us-west-2.amazonaws.com/eval_bundle.zip"
    core_bundle_dir: str = "${oc.env:NANOCHAT_BASE_DIR}/eval_bundle"
    core_checkpoint_path: Optional[str] = None


@dataclass
class Config:
    """Main configuration combining all components."""
    # Model settings (defined in model_base.py)
    model: Dict[str, Any] = field(default_factory=dict)

    # Training settings
    training: TrainingConfig = field(default_factory=TrainingConfig)

    # Data settings
    data: DataConfig = field(default_factory=DataConfig)

    # Logging settings
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # Optimizer settings (NEW: nanochat-style hybrid optimizer)
    optimizer: Dict[str, Any] = field(default_factory=dict)

    # Eval settings
    eval: EvalConfig = field(default_factory=EvalConfig)

    # Experiment info
    experiment_name: str = "default"
    output_dir: str = "outputs"

    # Metadata (for Hydra config groups)
    model_size_name: Optional[str] = None  # tiny, medium, large, etc.
    mlp_type_name: Optional[str] = None    # dense, gec, gec_shared, ec
    
    @classmethod
    def from_file(cls, path: str) -> "Config":
        """Load configuration from YAML or JSON file."""
        file_path = Path(path)
        
        if file_path.suffix == ".yaml" or file_path.suffix == ".yml":
            with open(file_path, "r") as f:
                data = yaml.safe_load(f)
        elif file_path.suffix == ".json":
            with open(file_path, "r") as f:
                data = json.load(f)
        else:
            raise ValueError(f"Unknown config file format: {file_path.suffix}")
        
        return cls.from_dict(data)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        """
        Create config from dictionary.

        Automatically filters out Hydra-specific metadata fields (presets, hydra, defaults)
        that are added during config composition.

        Args:
            data: Dictionary containing configuration values

        Returns:
            Config instance with validated settings
        """
        # Make a copy to avoid modifying the input
        data = data.copy()

        # Extract sub-configs
        model_cfg = data.pop("model", {})
        training_cfg = data.pop("training", {})
        data_cfg = data.pop("data", {})
        logging_cfg = data.pop("logging", {})
        optimizer_cfg = data.pop("optimizer", {})  # NEW: optimizer config
        eval_cfg = data.pop("eval", {})

        # Filter out Hydra-specific metadata that shouldn't be passed to dataclass
        # These are internal fields added by Hydra for config composition tracking
        hydra_metadata_keys = {"presets", "hydra", "defaults"}
        for key in hydra_metadata_keys:
            data.pop(key, None)

        # Backward-compat cleanup: legacy visualization knobs are removed.
        training_cfg.pop("enable_visualizations", None)
        training_cfg.pop("plot_interval", None)

        # Create sub-configs
        training = TrainingConfig(**training_cfg)
        data_config = DataConfig(**data_cfg)
        logging = LoggingConfig(**logging_cfg)
        eval_config = EvalConfig(**eval_cfg)

        # Create main config
        return cls(
            model=model_cfg,
            training=training,
            data=data_config,
            logging=logging,
            optimizer=optimizer_cfg,  # NEW: optimizer config
            eval=eval_config,
            **data
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        result = asdict(self)
        # Flatten for easier access
        result.update({
            "model": self.model,
            "training": asdict(self.training),
            "data": asdict(self.data),
            "logging": asdict(self.logging),
            "optimizer": self.optimizer,  # NEW: optimizer config
            "eval": asdict(self.eval),
        })
        return result
    
    def validate(self) -> None:
        """Validate configuration."""
        # Model validation (normalize aliases)
        model_type = self.model.get("model_type")
        if model_type == "tc":
            model_type = "scattermoe_tc"
            self.model["model_type"] = model_type

        assert model_type in ["dense", "gec", "gec_shared", "gec_shared_capacity", "ec", "ec_shared", "scattermoe_tc", "tc_shared"], \
            f"Invalid model type: {model_type}"
        if self.model.get("expert_parallel", False) and model_type not in ["gec", "gec_shared"]:
            raise ValueError("expert_parallel is only supported for model_type in ['gec', 'gec_shared']")
        
        # Router activation validation (if specified)
        if "router_activation" in self.model:
            assert self.model.get("router_activation") in ["sigmoid", "relu", "softmax_k", "softmax_e", "softmax_e_shared_out"], \
                f"Invalid router_activation: {self.model.get('router_activation')}"
            model_type = self.model.get("model_type")
            router_activation = self.model.get("router_activation")
            if model_type in ["scattermoe_tc", "tc_shared"] and router_activation == "softmax_k":
                raise ValueError("router_activation='softmax_k' is not allowed for token-choice routing")
            if model_type == "tc_shared" and router_activation == "softmax_e_shared_out":
                raise ValueError("router_activation='softmax_e_shared_out' is not allowed for tc_shared")

        if "load_balance_method" in self.model:
            assert self.model.get("load_balance_method") in ["none", "aux", "aux_error", "deepseek"], \
                f"Invalid load_balance_method: {self.model.get('load_balance_method')}"

        # Training validation
        assert self.training.total_batch_size > 0
        assert self.training.per_device_batch_size > 0
        assert self.training.sequence_length > 0

        # Threshold warmup/EMA validation:
        # Only enforced for threshold-capable routed expert-choice models.
        threshold_capable_models = {"gec", "gec_shared", "gec_shared_capacity", "ec_shared"}
        if model_type in threshold_capable_models:
            ema_start_steps = self.training.ema_start_steps
            threshold_warmup_steps = self.training.threshold_warmup_steps
            routing_mode = self.model.get("routing_mode", "topk")

            if ema_start_steps < 0:
                raise ValueError(
                    f"training.ema_start_steps must be >= 0, got {ema_start_steps}"
                )
            if threshold_warmup_steps < -1:
                raise ValueError(
                    "training.threshold_warmup_steps must be -1 (disabled) or >= 0, "
                    f"got {threshold_warmup_steps}"
                )
            if threshold_warmup_steps >= 0 and routing_mode != "topk":
                raise ValueError(
                    "training.threshold_warmup_steps requires model.routing_mode='topk' "
                    f"at startup, got routing_mode='{routing_mode}'"
                )
            if threshold_warmup_steps >= 0 and ema_start_steps > threshold_warmup_steps:
                raise ValueError(
                    f"training.ema_start_steps ({ema_start_steps}) must be <= "
                    f"training.threshold_warmup_steps ({threshold_warmup_steps})"
                )

            total_steps = self.training.calculate_max_steps()
            if ema_start_steps >= total_steps:
                raise ValueError(
                    f"training.ema_start_steps ({ema_start_steps}) must be < total_steps ({total_steps})"
                )
            if threshold_warmup_steps >= 0 and threshold_warmup_steps >= total_steps:
                raise ValueError(
                    "training.threshold_warmup_steps "
                    f"({threshold_warmup_steps}) must be < total_steps ({total_steps})"
                )
        
        # Data validation
        if not Path(self.data.data_path).exists():
            raise ValueError(f"Data path does not exist: {self.data.data_path}")
        if not Path(self.data.tokenizer_dir).exists():
            raise ValueError(f"Tokenizer path does not exist: {self.data.tokenizer_dir}")
        if self.data.tokenizer_type != "rustbpe":
            raise ValueError(f"Unsupported tokenizer_type: {self.data.tokenizer_type}")
    
    def get_total_batch_size(self) -> int:
        """Calculate total batch size including gradient accumulation."""
        return (
            self.training.total_batch_size
        )


# Preset configurations
PRESETS = {
    "dense-small": {
        "model": {
            "model_type": "dense",
            "n_layer": 12,
            "n_head": 8,
            "n_embd": 512,
        },
        "training": {
            "total_batch_size": 65536,
            "per_device_batch_size": 16,
            "max_steps": 5000,
        }
    },
}


def get_config(
    config_path: Optional[str] = None,
    preset: Optional[str] = None,
    overrides: Optional[Dict[str, Any]] = None
) -> Config:
    """
    Get configuration from file, preset, or create default.

    DEPRECATED: This function is kept for backward compatibility.
    New code should use Hydra's @hydra.main() decorator instead.

    Args:
        config_path: Path to config file
        preset: Name of preset configuration
        overrides: Dictionary of values to override

    Returns:
        Validated configuration
    """
    if config_path:
        config = Config.from_file(config_path)
    elif preset:
        if preset not in PRESETS:
            raise ValueError(f"Unknown preset: {preset}. Available: {list(PRESETS.keys())}")
        config = Config.from_dict(PRESETS[preset])
    else:
        config = Config()

    # Apply overrides
    if overrides:
        for key, value in overrides.items():
            # Handle nested keys like "training.total_batch_size"
            parts = key.split(".")
            target = config
            for part in parts[:-1]:
                target = getattr(target, part)
            # Handle both dict and object attributes
            if isinstance(target, dict):
                target[parts[-1]] = value
            else:
                setattr(target, parts[-1], value)

    # Validate
    config.validate()

    return config


# Register structured configs with Hydra
def register_configs() -> None:
    """Register all dataclass configs with Hydra's ConfigStore."""
    cs = ConfigStore.instance()

    # Register the main config
    cs.store(name="config_schema", node=Config)

    # Register sub-configs
    cs.store(group="schema/training", name="base", node=TrainingConfig)
    cs.store(group="schema/data", name="base", node=DataConfig)
    cs.store(group="schema/logging", name="base", node=LoggingConfig)
    cs.store(group="schema/eval", name="base", node=EvalConfig)


# Auto-register configs when module is imported
register_configs() 
