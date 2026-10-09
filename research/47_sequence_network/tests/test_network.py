"""Train-only statistics, gradient correctness and deterministic recurrent inference."""

from importlib import import_module
import unittest

import numpy as np
import torch

n = import_module("research.47_sequence_network.network")


class NetworkTests(unittest.TestCase):
    def setUp(self):
        generator = np.random.default_rng(11)
        self.sequence = generator.normal(size=(48, 30, 5)).astype(np.float32)
        self.context = generator.normal(size=(48, 3)).astype(np.float32)
        self.target = (self.sequence[:, -1, 0] * 3 + self.context[:, 0]).astype(np.float32)

    def test_scaler_uses_only_fit_inputs_and_does_not_mutate(self):
        scaler = n.Scaler.fit(self.sequence, self.context, self.target)
        expected_mean = self.sequence.astype(float).mean(axis=(0, 1))
        np.testing.assert_array_equal(scaler.sequence_mean, expected_mean)
        before = repr(scaler)
        extreme_sequence, extreme_context = self.sequence * 1000, self.context - 2000
        seq, ctx = scaler.transform(extreme_sequence, extreme_context)
        self.assertEqual(before, repr(scaler))
        self.assertLessEqual(float(np.abs(seq).max()), 10)
        self.assertLessEqual(float(np.abs(ctx).max()), 10)
        np.testing.assert_array_equal(scaler.sequence_mean, expected_mean)

    def test_scaler_rejects_nonfinite_boundary_inputs(self):
        bad = self.sequence.copy()
        bad[0, 0, 0] = np.nan
        with self.assertRaises(ValueError):
            n.Scaler.fit(bad, self.context, self.target)

    def test_forward_gru_gradient_matches_finite_difference(self):
        n.deterministic(17)
        model = n.ForecastNetwork("gru", 5, 3).double()
        sequence = torch.tensor(self.sequence[:2], dtype=torch.float64, requires_grad=True)
        context = torch.tensor(self.context[:2], dtype=torch.float64)
        prediction = model(sequence, context).sum()
        prediction.backward()
        index = (0, 29, 0)
        epsilon = 1e-5
        with torch.no_grad():
            plus, minus = sequence.detach().clone(), sequence.detach().clone()
            plus[index] += epsilon
            minus[index] -= epsilon
            numerical = float((model(plus, context).sum() - model(minus, context).sum()) / (2 * epsilon))
        self.assertAlmostEqual(float(sequence.grad[index]), numerical, delta=1e-7)

    def test_inference_is_independent_of_future_rows(self):
        n.deterministic(29)
        model = n.ForecastNetwork("gru", 5, 3)
        expected = n.predict_normalized(model, self.sequence[:10], self.context[:10])
        mutated = self.sequence.copy()
        mutated[10:] = 1000
        actual = n.predict_normalized(model, mutated, self.context)
        np.testing.assert_allclose(expected, actual[:10], rtol=0, atol=1e-7)

    def test_fitting_and_selected_checkpoint_are_deterministic(self):
        args = ("gru", 17, self.sequence[:32], self.context[:32], self.target[:32],
                self.sequence[32:], self.context[32:], self.target[32:])
        first, first_report = n.fit_network(*args, max_epochs=2)
        second, second_report = n.fit_network(*args, max_epochs=2)
        self.assertEqual(first_report, second_report)
        np.testing.assert_array_equal(n.predict_normalized(first, self.sequence, self.context),
                                      n.predict_normalized(second, self.sequence, self.context))
        selected = first_report["selected_epoch"] - 1
        self.assertEqual(first_report["history"][selected]["validation_mse"],
                         first_report["selected_validation_mse"])

    def test_neural_tabular_summaries_match_numpy_control(self):
        expected = n.tabular(self.sequence, self.context)
        actual = torch.cat((torch.from_numpy(self.context), torch.from_numpy(self.sequence).mean(dim=1),
                            torch.from_numpy(self.sequence).std(dim=1, correction=0),
                            torch.from_numpy(self.sequence)[:, -1], torch.from_numpy(self.sequence).sum(dim=1)), dim=1)
        np.testing.assert_allclose(expected, actual.numpy(), rtol=1e-6, atol=1e-6)

    def test_ridge_recovers_simple_signal_and_rejects_bad_target(self):
        fitted = n.fit_ridge(self.context, self.context[:, 0] * 2)
        predicted = n.ridge_predict(self.context, fitted)
        self.assertLess(float(np.sqrt(np.mean((predicted - self.context[:, 0] * 2) ** 2))), .05)
        with self.assertRaises(ValueError):
            n.fit_ridge(self.context, np.full(48, np.nan))


if __name__ == "__main__":
    unittest.main()
