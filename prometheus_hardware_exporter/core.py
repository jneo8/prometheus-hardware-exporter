"""Module for collecter core codes."""

from abc import abstractmethod
from dataclasses import dataclass
from logging import getLogger
from typing import Dict, Iterable, List, Optional, Type

from prometheus_client.metrics_core import Metric
from prometheus_client.registry import Collector

from .config import Config

logger = getLogger(__name__)


@dataclass
class Payload:
    """Container of data for each timeseries."""

    name: str
    value: float
    labels: List[str]
    uuid: str = ""  # timeseries's name

    def __post_init__(self) -> None:
        """Create uuid based on metric name and labels."""
        self.uuid = f"{self.name}({self.labels})"


@dataclass
class Specification:
    """Specification for metrics."""

    name: str
    labels: List[str]
    documentation: str
    metric_class: Type[Metric]


class BlockingCollector(Collector):
    """Base class for blocking collector.

    BlockingCollector base class is intended to be used when the collector is
    fetching data in a blocking fashion. For example, if the fetching process
    is reading data from files.
    """

    def __init__(self, config: Optional[Config] = None) -> None:
        """Initialize the class."""
        self.config = config
        self._datastore: Dict[str, Payload] = {}
        self._specs = {spec.name: spec for spec in self.specifications}

    @abstractmethod
    def fetch(self) -> List[Payload]:
        """User defined method for fetching data.

        User should defined their own method for loading data synchronously.
        The return should be a list of `Payload` class; the return value will
        be passed to user defined `process` method that should define how the
        data are used to update the metris.

        Returns:
            A list of payloads to be processed.
        """

    @abstractmethod
    def process(self, payloads: List[Payload], datastore: Dict[str, Payload]) -> List[Payload]:
        """User defined method for processing the fetched data.

        User should defined their own method for processing payloads. This
        includes how to update the metrics using the payloads, and returns the
        processed payload.

        Args:
            payloads: the fetched data to be processed.
            datastore: the data store for holding previous payloads.

        Returns:
            The proecssed payloads.
        """

    @property
    @abstractmethod
    def specifications(self) -> List[Specification]:
        """User defined property that defines the metrics.

        Returns:
            A list of specification.
        """

    def init_default_datastore(self, payloads: List[Payload]) -> None:
        """Initialize or fill data the store with default values.

        Args:
            payloads: the fetched data to be processed.
        """
        for payload in payloads:
            if payload.uuid not in self._datastore:
                self._datastore[payload.uuid] = Payload(
                    name=payload.name, labels=payload.labels, value=0.0
                )

    def collect(self) -> Iterable[Metric]:
        """Fetch data and update the internal metrics.

        This is a callback method that is used internally within
        `prometheus_client` every time the exporter server is queried. There is
        not return values for this method but it needs to yield all the metrics.

        Yields:
            metrics: the internal metrics
        """
        payloads = self.fetch()
        self.init_default_datastore(payloads)
        processed_payloads = self.process(payloads, self._datastore)

        # unpacked and create metrics
        for payload in processed_payloads:
            spec = self._specs[payload.name]
            # We have to ignore the type checking here, since the subclass of
            # any metric family from prometheus client adds new attributes and
            # methods.
            metric = spec.metric_class(  # type: ignore[call-arg]
                name=spec.name, labels=spec.labels, documentation=spec.documentation
            )
            metric.add_metric(  # type: ignore[attr-defined]
                labels=payload.labels, value=payload.value
            )
            yield metric
            self._datastore[payload.uuid] = payload
