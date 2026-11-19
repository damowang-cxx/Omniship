"use client";

import { useState } from "react";
import { Plus, X } from "lucide-react";
import type { AmsTemplateBillingConfig, AppUser, SupplierFieldRule } from "@/lib/types";
import styles from "./AmsTemplateEditor.module.css";

export function AmsTemplateEditor({ config, customers, fields, onChange }: {
  config: AmsTemplateBillingConfig | null;
  customers: AppUser[];
  fields: SupplierFieldRule[];
  onChange: (config: AmsTemplateBillingConfig | null) => void;
}) {
  const [newOption, setNewOption] = useState("");
  const [error, setError] = useState<string | null>(null);
  const matchingField = fields.find((field) =>
    (field.locatorMode === "column" && field.locatorValue.toUpperCase() === config?.matchColumn) ||
    (field.locatorMode === "header" && field.locatorValue.trim() === config?.matchHeader)
  );
  const options = Array.from(new Set([
    ...(config?.matchValues ?? []),
    ...(matchingField?.constraints.allowedValues ?? []),
    ...(config?.customerRates.flatMap((rate) => rate.fees.map((fee) => fee.matchValue)) ?? [])
  ]));
  const availableCustomers = customers.filter((customer) => customer.role === "user" && customer.status === "active"
    && !config?.customerRates.some((rate) => rate.userId === customer.id));

  const enable = () => {
    const weightField = fields.find((field) => field.semanticField === "weight_kg" && field.locatorMode === "column");
    onChange({
      taxHandlingFeeEur: "0.00", matchColumn: null, matchHeader: null,
      weightColumn: weightField?.locatorValue.toUpperCase() ?? null,
      matchValues: [], customerRates: []
    });
  };

  const addOption = () => {
    const value = newOption.trim();
    if (!config || !value) {
      setError("请输入 Excel 中的明细值");
      return;
    }
    if (options.includes(value)) {
      setError("该明细已在选项中");
      return;
    }
    onChange({ ...config, matchValues: [...options, value] });
    setNewOption("");
    setError(null);
  };

  const addCustomer = (userId: string) => {
    if (!config || !options.length || !availableCustomers.some((customer) => customer.id === userId)) return;
    onChange({ ...config, matchValues: options, customerRates: [{ userId, fees: [] }, ...config.customerRates] });
    setError(null);
  };

  return <section className={styles.container} aria-label="模板 AMS 扣费配置">
    <div className={styles.heading}><strong>AMS 扣费配置</strong><p>目的港为 AMS 时，按本模板的匹配列汇总各明细重量，再按客户单价收取 EUR 费用。</p></div>
    <label className={styles.toggle}>
      <input type="checkbox" checked={Boolean(config)} onChange={(event) => {
        setError(null);
        if (event.target.checked) enable(); else onChange(null);
      }} />启用本模板 AMS 扣费
    </label>
    {config && <>
      <div className={styles.columns}>
        <label>每票税金手续费 (EUR)<input aria-label="模板 AMS 每票税金手续费" min="0" required step="0.01" type="number" value={config.taxHandlingFeeEur}
          onChange={(event) => onChange({ ...config, taxHandlingFeeEur: event.target.value })} /></label>
        <label>指定匹配列<input aria-label="AMS 指定匹配列" autoCapitalize="characters" maxLength={3} pattern="[A-Za-z]{1,3}" placeholder="E" required={config.customerRates.length > 0} value={config.matchColumn ?? ""}
          onChange={(event) => onChange({ ...config, matchColumn: event.target.value.toUpperCase() || null })} /></label>
        <label>匹配列标题（选填）<input aria-label="AMS 匹配列标题" maxLength={255} placeholder="NETWORK" value={config.matchHeader ?? ""}
          onChange={(event) => onChange({ ...config, matchHeader: event.target.value || null })} /></label>
        <label>重量列 (kg)<input aria-label="AMS 重量列" autoCapitalize="characters" maxLength={3} pattern="[A-Za-z]{1,3}" placeholder="V" required={config.customerRates.length > 0} value={config.weightColumn ?? ""}
          onChange={(event) => onChange({ ...config, weightColumn: event.target.value.toUpperCase() || null })} /></label>
      </div>
      <div className={styles.options}>
        <strong>1. 定义收费明细</strong>
        <div className={styles.optionEntry}>
          <label>Excel 明细值<input aria-label="新增 AMS 明细值" maxLength={120} placeholder="例如 DE-DHL" value={newOption}
            onChange={(event) => setNewOption(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); addOption(); } }} /></label>
          <button onClick={addOption} type="button"><Plus size={14} />添加明细选项</button>
        </div>
        {options.length > 0 && <ul className={styles.optionList} aria-label="AMS 明细选项">
          {options.map((value) => <li key={value}>{value}</li>)}
        </ul>}
        <p className={styles.hint}>明细值与 Excel 单元格去除首尾空格后的内容精确匹配。这些选项在本模板内共用，单价在下方按客户分别设置。</p>
      </div>
      {error && <p className={styles.error} role="alert">{error}</p>}
      <div className={styles.customerEntry}>
        <strong>2. 按客户选择明细并报价</strong>
        <p className={styles.hint}>选择客户后即展开报价设置。每位客户可勾选多个明细；同一明细可为不同客户设置不同的 EUR/kg 单价。</p>
        <label>添加收费客户<select aria-label="AMS 添加客户" disabled={!options.length || !availableCustomers.length} value="" onChange={(event) => addCustomer(event.target.value)}>
          <option value="">{!options.length ? "请先添加上方收费明细" : !availableCustomers.length ? "暂无可添加客户" : "选择客户，设置明细与单价"}</option>
          {availableCustomers.map((customer) => <option key={customer.id} value={customer.id}>{customer.username} · {customer.email}</option>)}
        </select></label>
        {!config.customerRates.length && <p className={styles.empty}>尚未设置收费客户。先定义明细，再选择客户填写报价。</p>}
      </div>
      {config.customerRates.map((rate) => {
        const customer = customers.find((item) => item.id === rate.userId);
        const customerName = customer?.username || rate.userId;
        return <fieldset className={styles.customer} key={rate.userId}>
          <legend>{customerName}</legend>
          <div className={styles.customerHeading}><span>{customer?.email || "已删除客户"}</span>
            <button type="button" aria-label={`删除 ${customerName} AMS 收费设置`} onClick={() => onChange({ ...config, customerRates: config.customerRates.filter((item) => item.userId !== rate.userId) })}><X size={14} />删除客户</button>
          </div>
          <p className={styles.hint}>已选 {rate.fees.length} 项收费明细{!rate.fees.length ? "，请勾选下方明细并填写该客户的单价。" : "，以下报价仅适用于该客户。"}</p>
          {options.map((value) => {
            const fee = rate.fees.find((item) => item.matchValue === value);
            return <div className={styles.fee} data-selected={Boolean(fee)} key={value}>
              <label className={styles.toggle}><input type="checkbox" aria-label={`${customerName} 收取 ${value}`} checked={Boolean(fee)} onChange={(event) => onChange({
                ...config, matchValues: options,
                customerRates: config.customerRates.map((item) => item.userId === rate.userId ? {
                  ...item, fees: event.target.checked ? [...item.fees, { matchValue: value, rateEurPerKg: "" }] : item.fees.filter((candidate) => candidate.matchValue !== value)
                } : item)
              })} />{value}</label>
              <label>该客户单价 · EUR / kg<input aria-label={`${customerName} ${value} 每公斤报价`} disabled={!fee} min="0.01" placeholder={fee ? "填写单价" : "先勾选明细"} required={Boolean(fee)} step="0.01" type="number" value={fee?.rateEurPerKg ?? ""} onChange={(event) => onChange({
                ...config, customerRates: config.customerRates.map((item) => item.userId === rate.userId ? {
                  ...item, fees: item.fees.map((candidate) => candidate.matchValue === value ? { ...candidate, rateEurPerKg: event.target.value } : candidate)
                } : item)
              })} /></label>
            </div>;
          })}
        </fieldset>;
      })}
    </>}
  </section>;
}
