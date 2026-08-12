import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import i18n from "../i18n";
import RecommendationCard, { type Recommendation } from "./RecommendationCard";

const baseRec: Recommendation = {
  title: "Rinegozia il contratto con CloudNet Solutions",
  reason: "Spesa in aumento del 67.4%",
  supplier: "CloudNet Solutions",
  category: "Software & Digital Licenses",
  estimated_saving: 430.05,
  currency: "EUR",
  confidence: "medium",
  evidence: ["Storico spesa: €1,712.50 -> €2,867.00"],
};

describe("RecommendationCard", () => {
  describe("Italian (it)", () => {
    beforeEach(() => i18n.changeLanguage("it"));

    it("renders title, reason, supplier and category", () => {
      render(<RecommendationCard rec={baseRec} />);
      expect(screen.getByText(baseRec.title)).toBeInTheDocument();
      expect(screen.getByText(baseRec.reason)).toBeInTheDocument();
      expect(screen.getByText(/Fornitore: CloudNet Solutions/)).toBeInTheDocument();
      expect(screen.getByText(/Categoria: Software & Digital Licenses/)).toBeInTheDocument();
    });

    it("formats the estimated saving with the EUR symbol", () => {
      render(<RecommendationCard rec={baseRec} />);
      expect(screen.getByText(/€430.05|€430,05/)).toBeInTheDocument();
    });

    it("does not render an estimated-saving line when the value is null", () => {
      render(<RecommendationCard rec={{ ...baseRec, estimated_saving: null }} />);
      expect(screen.queryByText(/anno stimato/)).not.toBeInTheDocument();
    });

    it("renders every evidence line", () => {
      const rec = { ...baseRec, evidence: ["Evidence one", "Evidence two"] };
      render(<RecommendationCard rec={rec} />);
      expect(screen.getByText("Evidence one")).toBeInTheDocument();
      expect(screen.getByText("Evidence two")).toBeInTheDocument();
    });

    it("falls back to the raw currency code for a non-mapped currency", () => {
      render(<RecommendationCard rec={{ ...baseRec, currency: "CHF", estimated_saving: 100 }} />);
      expect(screen.getByText(/CHF/)).toBeInTheDocument();
    });
  });

  describe("English (en)", () => {
    beforeEach(() => i18n.changeLanguage("en"));

    it("renders supplier and category labels in English", () => {
      render(<RecommendationCard rec={baseRec} />);
      expect(screen.getByText(/Supplier: CloudNet Solutions/)).toBeInTheDocument();
      expect(screen.getByText(/Category: Software & Digital Licenses/)).toBeInTheDocument();
    });

    it("does not render an estimated-saving line when the value is null", () => {
      render(<RecommendationCard rec={{ ...baseRec, estimated_saving: null }} />);
      expect(screen.queryByText(/estimated per year/)).not.toBeInTheDocument();
    });
  });
});
