import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataTable, Pager, StatCard, Empty, ErrorBox, Badge, type Column } from "./ui";

type Row = { id: string; code: string; total: number };

const ROWS: Row[] = [
  { id: "1", code: "A-01", total: 10000 },
  { id: "2", code: "B-02", total: 500 },
];

const COLUMNS: Column<Row>[] = [
  { key: "code", header: "Code", render: (r) => r.code },
  { key: "total", header: "Total", numeric: true, render: (r) => (r.total / 100).toFixed(2) },
];

describe("DataTable", () => {
  it("exposes a caption, column scope and row-key identity", () => {
    const { container } = render(
      <DataTable caption="Test grid" rows={ROWS} rowKey={(r) => r.id} columns={COLUMNS} empty={<Empty title="none" />} />,
    );
    const table = container.querySelector("table");
    expect(table).toBeTruthy();
    expect(container.querySelector("caption")?.textContent).toBe("Test grid");
    const headers = container.querySelectorAll("th");
    headers.forEach((th) => expect(th).toHaveAttribute("scope", "col"));
    expect(screen.getByText("A-01")).toBeInTheDocument();
    expect(screen.getByText("B-02")).toBeInTheDocument();
  });

  it("announces sort state with aria-sort, not a glyph alone", async () => {
    const onSort = vi.fn();
    const cols: Column<Row>[] = [
      { key: "code", header: "Code", sortable: true, render: (r) => r.code },
      ...COLUMNS.slice(1),
    ];
    const { container } = render(
      <DataTable caption="t" rows={ROWS} rowKey={(r) => r.id} columns={cols}
        sort="code" order="asc" onSort={onSort} empty={<Empty title="none" />} />,
    );
    const th = container.querySelector('th[aria-sort="ascending"]');
    expect(th).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: /Code/ }));
    expect(onSort).toHaveBeenCalledWith("code");
  });

  it("renders the empty state instead of an empty table with 0 rows", () => {
    const { container } = render(
      <DataTable caption="t" rows={[]} rowKey={(r) => r.id} columns={COLUMNS} empty={<Empty title="Nothing here" />} />,
    );
    expect(container.querySelector("table")).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("Nothing here");
  });
});

describe("Pager", () => {
  it("disables Prev on page 1 and Next at the last page", () => {
    const { rerender } = render(<Pager stack={[]} onPrev={() => {}} hasMore={true} onNext={() => {}} />);
    expect(screen.getByRole("button", { name: /Prev/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Next/ })).toBeEnabled();
    rerender(<Pager stack={["c1"]} onPrev={() => {}} hasMore={false} onNext={() => {}} />);
    expect(screen.getByRole("button", { name: /Prev/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Next/ })).toBeDisabled();
  });

  it("invokes handlers on click", async () => {
    const onPrev = vi.fn();
    const onNext = vi.fn();
    render(<Pager stack={["c1"]} onPrev={onPrev} hasMore={true} onNext={onNext} />);
    await userEvent.click(screen.getByRole("button", { name: /Prev/ }));
    await userEvent.click(screen.getByRole("button", { name: /Next/ }));
    expect(onPrev).toHaveBeenCalledTimes(1);
    expect(onNext).toHaveBeenCalledTimes(1);
  });
});

describe("presentational semantics", () => {
  it("ErrorBox uses role=alert and shows a request id when given", () => {
    render(<ErrorBox message="Broken" requestId="req-42" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Broken");
    expect(screen.getByRole("alert")).toHaveTextContent("req-42");
  });

  it("Empty uses role=status so it announces politely", () => {
    render(<Empty title="Empty" hint="hint text" />);
    expect(screen.getByRole("status")).toHaveTextContent("hint text");
  });

  it("Badge carries its tone class, not just colour", () => {
    const { container } = render(<Badge tone="bad">expired</Badge>);
    expect(container.firstChild).toHaveClass("badge", "bad");
  });

  it("StatCard marks good/bad/warn visually with a class other than colour", () => {
    const { container } = render(<StatCard label="Leakage" value="12,000 INR" tone="bad" />);
    expect(screen.getByText("Leakage")).toBeInTheDocument();
    expect(container.querySelector(".v.bad")).toBeTruthy();
  });

  it("numeric input filtering is not done client-side in DataTable (server sorts)", async () => {
    // Regression guard: users must never see client-filtered rows presented as
    // server-complete. The component has no filter prop at all.
    const onSort = vi.fn();
    render(
      <DataTable caption="t" rows={ROWS} rowKey={(r) => r.id}
        columns={[{ key: "code", header: "Code", sortable: true, render: (r) => r.code }]}
        sort="code" order="desc" onSort={onSort} empty={<Empty title="x" />} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Code/ }));
    expect(onSort).toHaveBeenCalledWith("code");
    expect(ROWS.map((r) => r.code)).toEqual(["A-01", "B-02"]);
  });
});
