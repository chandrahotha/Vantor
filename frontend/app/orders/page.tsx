import type { Metadata } from "next";
import { OrdersPage } from "../shared/orders";

export const metadata: Metadata = {
  title: "Purchase orders",
  description:
    "Requisition to invoice: purchase orders, tiered approvals, segregation of duties, budget gates, goods receipt and server-side three-way match.",
  alternates: { canonical: "/orders" },
};

export default OrdersPage;
