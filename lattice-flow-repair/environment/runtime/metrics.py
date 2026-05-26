"""
Evaluation Metrics Module
==========================
Computes precision, recall, F1, and other evaluation metrics by comparing
the correlation engine's output against ground truth labels. Supports
per-class and aggregate metrics computation.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .correlator import CorrelationResult, CLASSIFICATION_CAUSAL, CLASSIFICATION_INDEPENDENT
from .events import GroundTruthLabels


@dataclass
class ConfusionMatrix:
    """Standard confusion matrix for binary classification."""
    true_positives: int = 0
    false_positives: int = 0
    true_negatives: int = 0
    false_negatives: int = 0

    @property
    def total(self) -> int:
        return (
            self.true_positives
            + self.false_positives
            + self.true_negatives
            + self.false_negatives
        )

    @property
    def accuracy(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.true_positives + self.true_negatives) / self.total

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        if denom == 0:
            return 0.0
        return self.true_positives / denom

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        if denom == 0:
            return 0.0
        return self.true_positives / denom

    @property
    def f1_score(self) -> float:
        p, r = self.precision, self.recall
        if p + r == 0:
            return 0.0
        return 2.0 * p * r / (p + r)

    @property
    def specificity(self) -> float:
        denom = self.true_negatives + self.false_positives
        if denom == 0:
            return 0.0
        return self.true_negatives / denom

    @property
    def negative_predictive_value(self) -> float:
        denom = self.true_negatives + self.false_negatives
        if denom == 0:
            return 0.0
        return self.true_negatives / denom

    def to_dict(self) -> Dict:
        return {
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "true_negatives": self.true_negatives,
            "false_negatives": self.false_negatives,
            "accuracy": round(self.accuracy, 4),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4),
            "specificity": round(self.specificity, 4),
        }


@dataclass
class EvaluationReport:
    """Complete evaluation report comparing predictions to ground truth."""
    confusion_matrix: ConfusionMatrix = field(default_factory=ConfusionMatrix)
    per_service_precision: Dict[str, float] = field(default_factory=dict)
    per_service_recall: Dict[str, float] = field(default_factory=dict)
    total_evaluated: int = 0
    total_skipped: int = 0
    causal_predicted: int = 0
    independent_predicted: int = 0
    causal_actual: int = 0
    independent_actual: int = 0

    @property
    def precision(self) -> float:
        return self.confusion_matrix.precision

    @property
    def recall(self) -> float:
        return self.confusion_matrix.recall

    @property
    def f1_score(self) -> float:
        return self.confusion_matrix.f1_score

    def to_dict(self) -> Dict:
        return {
            "confusion_matrix": self.confusion_matrix.to_dict(),
            "total_evaluated": self.total_evaluated,
            "total_skipped": self.total_skipped,
            "causal_predicted": self.causal_predicted,
            "independent_predicted": self.independent_predicted,
            "causal_actual": self.causal_actual,
            "independent_actual": self.independent_actual,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1_score": round(self.f1_score, 4),
        }


class MetricsEvaluator:
    """
    Evaluates correlation engine output against ground truth labels.

    Treats 'causal' as the positive class and 'independent' as negative.
    - True Positive: predicted causal, actually causal
    - False Positive: predicted causal, actually independent
    - True Negative: predicted independent, actually independent
    - False Negative: predicted independent, actually causal
    """

    def __init__(self, ground_truth: GroundTruthLabels):
        self._ground_truth = ground_truth

    def evaluate(self, results: List[CorrelationResult]) -> EvaluationReport:
        """
        Compare correlation results against ground truth and compute metrics.
        """
        report = EvaluationReport()
        cm = ConfusionMatrix()

        for result in results:
            predicted = result.classification
            actual = self._ground_truth.get_label(result.event_a_id, result.event_b_id)

            if actual is None:
                report.total_skipped += 1
                continue

            report.total_evaluated += 1

            if predicted == CLASSIFICATION_CAUSAL:
                report.causal_predicted += 1
            else:
                report.independent_predicted += 1

            if actual == "causal":
                report.causal_actual += 1
            else:
                report.independent_actual += 1

            if predicted == CLASSIFICATION_CAUSAL and actual == "causal":
                cm.true_positives += 1
            elif predicted == CLASSIFICATION_CAUSAL and actual == "independent":
                cm.false_positives += 1
            elif predicted == CLASSIFICATION_INDEPENDENT and actual == "independent":
                cm.true_negatives += 1
            elif predicted == CLASSIFICATION_INDEPENDENT and actual == "causal":
                cm.false_negatives += 1

        report.confusion_matrix = cm
        return report

    def evaluate_per_service(
        self,
        results: List[CorrelationResult],
        event_service_map: Dict[str, str],
    ) -> Dict[str, ConfusionMatrix]:
        """Compute per-service confusion matrices."""
        service_cms: Dict[str, ConfusionMatrix] = {}

        for result in results:
            actual = self._ground_truth.get_label(result.event_a_id, result.event_b_id)
            if actual is None:
                continue

            # Attribute to both services
            for event_id in [result.event_a_id, result.event_b_id]:
                service = event_service_map.get(event_id)
                if not service:
                    continue
                if service not in service_cms:
                    service_cms[service] = ConfusionMatrix()
                cm = service_cms[service]

                predicted = result.classification
                if predicted == CLASSIFICATION_CAUSAL and actual == "causal":
                    cm.true_positives += 1
                elif predicted == CLASSIFICATION_CAUSAL and actual == "independent":
                    cm.false_positives += 1
                elif predicted == CLASSIFICATION_INDEPENDENT and actual == "independent":
                    cm.true_negatives += 1
                elif predicted == CLASSIFICATION_INDEPENDENT and actual == "causal":
                    cm.false_negatives += 1

        return service_cms

    def compute_threshold_curve(
        self, results: List[CorrelationResult], thresholds: Optional[List[float]] = None
    ) -> List[Dict[str, float]]:
        """
        Compute precision/recall at various confidence thresholds.
        Useful for finding optimal threshold.
        """
        if thresholds is None:
            thresholds = [0.1 * i for i in range(1, 10)]

        curve = []
        for threshold in thresholds:
            cm = ConfusionMatrix()
            for result in results:
                actual = self._ground_truth.get_label(result.event_a_id, result.event_b_id)
                if actual is None:
                    continue

                # Re-classify at this threshold
                if result.confidence >= threshold and result.classification == CLASSIFICATION_CAUSAL:
                    predicted = CLASSIFICATION_CAUSAL
                else:
                    predicted = CLASSIFICATION_INDEPENDENT

                if predicted == CLASSIFICATION_CAUSAL and actual == "causal":
                    cm.true_positives += 1
                elif predicted == CLASSIFICATION_CAUSAL and actual == "independent":
                    cm.false_positives += 1
                elif predicted == CLASSIFICATION_INDEPENDENT and actual == "independent":
                    cm.true_negatives += 1
                elif predicted == CLASSIFICATION_INDEPENDENT and actual == "causal":
                    cm.false_negatives += 1

            curve.append({
                "threshold": threshold,
                "precision": cm.precision,
                "recall": cm.recall,
                "f1": cm.f1_score,
            })

        return curve

    def compute_ranking_metrics(
        self, results: List[CorrelationResult]
    ) -> Dict[str, float]:
        """
        Compute ranking-based metrics (average precision, NDCG) treating
        confidence scores as ranking values.
        """
        # Sort by confidence descending
        scored_pairs = []
        for result in results:
            actual = self._ground_truth.get_label(result.event_a_id, result.event_b_id)
            if actual is None:
                continue
            is_relevant = actual == "causal"
            scored_pairs.append((result.confidence, is_relevant))

        scored_pairs.sort(key=lambda x: -x[0])

        # Average precision
        relevant_count = 0
        precision_sum = 0.0
        for i, (score, relevant) in enumerate(scored_pairs, 1):
            if relevant:
                relevant_count += 1
                precision_sum += relevant_count / i

        total_relevant = sum(1 for _, r in scored_pairs if r)
        avg_precision = precision_sum / total_relevant if total_relevant > 0 else 0.0

        return {
            "average_precision": round(avg_precision, 4),
            "total_relevant": total_relevant,
            "total_evaluated": len(scored_pairs),
        }


def quick_evaluate(
    results: List[CorrelationResult], ground_truth: GroundTruthLabels
) -> Dict[str, float]:
    """
    Quick evaluation returning just precision, recall, and F1.
    """
    evaluator = MetricsEvaluator(ground_truth)
    report = evaluator.evaluate(results)
    return {
        "precision": report.precision,
        "recall": report.recall,
        "f1_score": report.f1_score,
    }


def compute_error_analysis(
    results: List[CorrelationResult], ground_truth: GroundTruthLabels
) -> Dict[str, List[Tuple[str, str]]]:
    """
    Identify specific error cases for debugging.
    Returns dict with 'false_positives' and 'false_negatives' lists.
    """
    fps: List[Tuple[str, str]] = []
    fns: List[Tuple[str, str]] = []

    for result in results:
        actual = ground_truth.get_label(result.event_a_id, result.event_b_id)
        if actual is None:
            continue

        if result.classification == CLASSIFICATION_CAUSAL and actual == "independent":
            fps.append((result.event_a_id, result.event_b_id))
        elif result.classification == CLASSIFICATION_INDEPENDENT and actual == "causal":
            fns.append((result.event_a_id, result.event_b_id))

    return {"false_positives": fps, "false_negatives": fns}
