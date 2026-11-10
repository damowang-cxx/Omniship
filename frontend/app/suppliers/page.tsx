"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  CheckCircle2,
  CircleDollarSign,
  Factory,
  FileSpreadsheet,
  History,
  Plus,
  Save,
  Settings2,
  X
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import {
  applyRetroactiveBilling,
  createSupplier,
  getBillingSettings,
  getCurrentUser,
  getLhrBillingSettings,
  isUnauthorizedError,
  listUsers,
  listSuppliers,
  logout,
  publishSupplierVersion,
  updateBillingSettings,
  updateLhrBillingSettings,
  updateSupplier
} from "@/lib/api";
import type {
  AppUser,
  LhrBillingConfig,
  LhrBillingSettingsItem,
  LhrSurchargeRule,
  SupplierFieldRule,
  SupplierItem,
  SupplierSemanticField,
  SupplierVersionConfig,
  RetroactiveBillingResponse
} from "@/lib/types";
import styles from "./page.module.css";

function newRule(index: number): SupplierFieldRule {
  return {
    key: `field_${Date.now()}_${index}`,
    name: "New rule",
    semanticField: null,
    locatorMode: "column",
    locatorValue: "A",
    valueType: "text",
    blankPolicy: "allow",
    caseInsensitive: false,
    allowUnknownCountry: true,
    countryAliases: {},
    constraints: {
      minValue: null,
      maxValue: null,
      minLength: null,
      maxLength: null,
      pattern: null,
      allowedValues: [],
      unique: false
    }
  };
}

function emptyConfig(): SupplierVersionConfig {
  const first = newRule(0);
  first.key = "row_identifier";
  first.name = "Row identifier";
  first.semanticField = "parcel_unit_number";
  return {
    workbook: {
      sheetMode: "first",
      sheetName: null,
      headerRow: 1,
      dataStartRow: 2
    },
    fields: [first],
    lhrBilling: null,
    billingGroupColumn: "A",
    billingDistinctColumn: "A"
  };
}

function cloneConfig(config: SupplierVersionConfig): SupplierVersionConfig {
  return JSON.parse(JSON.stringify(config)) as SupplierVersionConfig;
}

function legacyBillingColumn(
  config: SupplierVersionConfig,
  fieldKey: string | null | undefined
): string {
  const field = config.fields.find((candidate) => candidate.key === fieldKey);
  return field?.locatorMode === "column" ? field.locatorValue.toUpperCase() : "";
}

function independentDeductionConfig(
  config: SupplierVersionConfig
): SupplierVersionConfig {
  const groupColumn = (
    config.billingGroupColumn ||
    legacyBillingColumn(config, config.billingGroupFieldKey) ||
    legacyBillingColumn(config, config.rowKeyFieldKey)
  ).trim().toUpperCase();
  const distinctColumn = (
    config.billingDistinctColumn ||
    legacyBillingColumn(config, config.billingDistinctFieldKey) ||
    groupColumn
  ).trim().toUpperCase();
  return {
    workbook: config.workbook,
    fields: config.fields,
    lhrBilling: null,
    billingGroupColumn: groupColumn,
    billingDistinctColumn: distinctColumn
  };
}

function billingColumnLabel(
  config: SupplierVersionConfig,
  kind: "group" | "distinct"
): string {
  const direct = kind === "group"
    ? config.billingGroupColumn
    : config.billingDistinctColumn;
  if (direct) return `Column ${direct}`;
  const legacyKey = kind === "group"
    ? config.billingGroupFieldKey || config.rowKeyFieldKey
    : config.billingDistinctFieldKey;
  const legacyRule = config.fields.find((field) => field.key === legacyKey);
  if (!legacyRule) return "-";
  return legacyRule.locatorMode === "column"
    ? `Column ${legacyRule.locatorValue} (legacy)`
    : `Header ${legacyRule.locatorValue} (legacy)`;
}

function formula(rule: SupplierFieldRule) {
  const parts = [];
  if (rule.blankPolicy === "required") parts.push("required(x)");
  if (rule.blankPolicy === "skip_row") parts.push("blank(x) => skip row");
  parts.push(`${rule.valueType}(x)`);
  if (rule.constraints.minValue !== null && rule.constraints.minValue !== undefined && rule.constraints.minValue !== "") {
    parts.push(`x >= ${rule.constraints.minValue}`);
  }
  if (rule.constraints.maxValue !== null && rule.constraints.maxValue !== undefined && rule.constraints.maxValue !== "") {
    parts.push(`x <= ${rule.constraints.maxValue}`);
  }
  if (rule.constraints.minLength != null) parts.push(`length(x) >= ${rule.constraints.minLength}`);
  if (rule.constraints.maxLength != null) parts.push(`length(x) <= ${rule.constraints.maxLength}`);
  if (rule.constraints.pattern) parts.push(`matches(${rule.constraints.pattern})`);
  if (rule.constraints.allowedValues.length) parts.push(`in(${rule.constraints.allowedValues.join(", ")})`);
  if (rule.constraints.unique) parts.push("unique(x)");
  return parts.join(" AND ");
}

export default function SuppliersPage() {
  const router = useRouter();
  const [user, setUser] = useState<AppUser | null>(null);
  const [suppliers, setSuppliers] = useState<SupplierItem[]>([]);
  const [customers, setCustomers] = useState<AppUser[]>([]);
  const [customerDialog, setCustomerDialog] = useState<{ userId: string; rate: string; editing: boolean } | null>(null);
  const [customerDialogError, setCustomerDialogError] = useState<string | null>(null);
  const [unitRate, setUnitRate] = useState("3.00");
  const [airportText, setAirportText] = useState("AMS");
  const [taxEffectiveDate, setTaxEffectiveDate] = useState("2026-07-01");
  const [isLoading, setIsLoading] = useState(true);
  const [notice, setNotice] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [editing, setEditing] = useState<SupplierItem | null | "new">(null);
  const [lhrEditing, setLhrEditing] = useState(false);
  const [lhrSettings, setLhrSettings] = useState<LhrBillingSettingsItem | null>(null);
  const [lhrDraft, setLhrDraft] = useState<LhrBillingConfig | null>(null);
  const [lhrError, setLhrError] = useState<string | null>(null);
  const [isLhrSaving, setIsLhrSaving] = useState(false);
  const [draftName, setDraftName] = useState("");
  const [draftConfig, setDraftConfig] = useState<SupplierVersionConfig>(emptyConfig());
  const [isSaving, setIsSaving] = useState(false);
  const [isRetroactiveOpen, setIsRetroactiveOpen] = useState(false);
  const [retroactiveText, setRetroactiveText] = useState("");
  const [retroactiveResult, setRetroactiveResult] = useState<RetroactiveBillingResponse | null>(null);
  const [isProcessingRetroactive, setIsProcessingRetroactive] = useState(false);

  const load = useCallback(async () => {
    try {
      const account = await getCurrentUser();
      if (account.user.role !== "admin") {
        router.replace("/waybill-uploads");
        return;
      }
      const [supplierResponse, settings, userResponse, lhrResponse] = await Promise.all([
        listSuppliers(),
        getBillingSettings(),
        listUsers(),
        getLhrBillingSettings()
      ]);
      setUser(account.user);
      setSuppliers(supplierResponse.items);
      setCustomers(userResponse.items);
      setLhrSettings(lhrResponse);
      setUnitRate(settings.unitTaxEur);
      setAirportText(settings.taxableAirports.join(", "));
      setTaxEffectiveDate(settings.taxEffectiveDate);
    } catch (error) {
      if (isUnauthorizedError(error)) {
        router.replace("/");
        return;
      }
      setNotice({ tone: "error", text: error instanceof Error ? error.message : "Unable to load suppliers" });
    } finally {
      setIsLoading(false);
    }
  }, [router]);

  useEffect(() => {
    void load();
  }, [load]);

  const openNew = () => {
    setLhrEditing(false);
    setEditing("new");
    setDraftName("");
    setDraftConfig(emptyConfig());
  };

  const openEdit = (supplier: SupplierItem) => {
    setLhrEditing(false);
    setEditing(supplier);
    setDraftName(supplier.name);
    setDraftConfig(independentDeductionConfig(cloneConfig(supplier.currentVersion.config)));
  };

  const openLhrEdit = () => {
    setEditing(null);
    setLhrEditing(true);
    setLhrDraft(lhrSettings?.config ? JSON.parse(JSON.stringify(lhrSettings.config)) as LhrBillingConfig : null);
    setLhrError(null);
    setCustomerDialog(null);
  };

  const updateRule = (index: number, updater: (rule: SupplierFieldRule) => SupplierFieldRule) => {
    setDraftConfig((current) => ({
      ...current,
      fields: current.fields.map((rule, ruleIndex) => ruleIndex === index ? updater(rule) : rule)
    }));
  };

  const removeRule = (index: number) => {
    setDraftConfig((current) => {
      if (current.fields.length === 1) return current;
      const fields = current.fields.filter((_, ruleIndex) => ruleIndex !== index);
      return { ...current, fields };
    });
  };

  const setLhrBilling = (updater: (billing: LhrBillingConfig) => LhrBillingConfig) => {
    setLhrDraft((current) => current ? updater(current) : null);
  };

  const updateSurchargeRule = (index: number, updater: (rule: LhrSurchargeRule) => LhrSurchargeRule) => {
    setLhrBilling((billing) => ({ ...billing, surchargeRules: billing.surchargeRules.map((rule, i) => i === index ? updater(rule) : rule) }));
  };

  const addSurchargeRule = (mode: LhrSurchargeRule["mode"]) => {
    setLhrBilling((billing) => ({ ...billing, surchargeRules: [...billing.surchargeRules, {
      name: "", mode, prefixes: [], amountGbp: mode === "fixed" ? "" : null,
      bands: mode === "weight_bands" ? [{ minWeightKg: 0, maxWeightKg: null, amountGbp: "" }] : []
    }] }));
  };

  const confirmCustomerRate = () => {
    if (!customerDialog || !customerDialog.userId) {
      setCustomerDialogError("请选择客户");
      return;
    }
    if (!/^\d+(\.\d{1,2})?$/.test(customerDialog.rate) || Number(customerDialog.rate) <= 0) {
      setCustomerDialogError("请输入大于 0、最多两位小数的 GBP/kg 报价");
      return;
    }
    if (!customerDialog.editing && lhrDraft?.customerRates.some((rate) => rate.userId === customerDialog.userId)) {
      setCustomerDialogError("该客户已在列表中");
      return;
    }
    setLhrBilling((billing) => ({ ...billing, customerRates: customerDialog.editing
      ? billing.customerRates.map((rate) => rate.userId === customerDialog.userId ? { ...rate, rateGbpPerKg: customerDialog.rate } : rate)
      : [...billing.customerRates, { userId: customerDialog.userId, rateGbpPerKg: customerDialog.rate }]
    }));
    setCustomerDialog(null);
    setCustomerDialogError(null);
  };

  const handleSaveSettings = async (event: FormEvent) => {
    event.preventDefault();
    setNotice(null);
    try {
      const airports = airportText.split(/[,\s]+/).map((value) => value.trim()).filter(Boolean);
      const settings = await updateBillingSettings(unitRate, airports, taxEffectiveDate);
      setUnitRate(settings.unitTaxEur);
      setAirportText(settings.taxableAirports.join(", "));
      setTaxEffectiveDate(settings.taxEffectiveDate);
      setNotice({ tone: "success", text: "Billing settings saved" });
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof Error ? error.message : "Unable to save billing settings" });
    }
  };

  const handleRetroactiveBilling = async (event: FormEvent) => {
    event.preventDefault();
    const waybillNumbers = retroactiveText.split(/\s+/).map((value) => value.trim()).filter(Boolean);
    if (!waybillNumbers.length) {
      setNotice({ tone: "error", text: "Enter at least one waybill number" });
      return;
    }
    setIsProcessingRetroactive(true);
    setRetroactiveResult(null);
    setNotice(null);
    try {
      const result = await applyRetroactiveBilling(waybillNumbers);
      setRetroactiveResult(result);
      setNotice({
        tone: result.failedCount ? "error" : "success",
        text: `${result.succeededCount} customs deductions recorded; ${result.failedCount} failed`
      });
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof Error ? error.message : "Unable to process retroactive customs" });
    } finally {
      setIsProcessingRetroactive(false);
    }
  };

  const handleSaveSupplier = async (event: FormEvent) => {
    event.preventDefault();
    if (!editing) return;
    setIsSaving(true);
    setNotice(null);
    const normalizedConfig = independentDeductionConfig(draftConfig);
    setDraftConfig(normalizedConfig);
    try {
      if (editing === "new") {
        await createSupplier(draftName, normalizedConfig);
      } else {
        if (draftName.trim() !== editing.name) {
          await updateSupplier(editing.id, { name: draftName.trim() });
        }
        await publishSupplierVersion(editing.id, normalizedConfig);
      }
      setEditing(null);
      await load();
      setNotice({ tone: "success", text: editing === "new" ? "Supplier created" : "New supplier version published" });
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof Error ? error.message : "Unable to save supplier" });
    } finally {
      setIsSaving(false);
    }
  };

  const handleSaveLhr = async (event: FormEvent) => {
    event.preventDefault();
    if (!lhrEditing) return;
    setLhrError(null);
    if (lhrDraft) {
      const prefixes = lhrDraft.surchargeRules.flatMap((rule) => rule.prefixes);
      if (prefixes.length !== new Set(prefixes).size) {
        setLhrError("同一提单前三位不能出现在多条货站附加费规则中");
        return;
      }
    }
    setIsLhrSaving(true);
    try {
      const saved = await updateLhrBillingSettings(lhrDraft);
      setLhrSettings(saved);
      setLhrEditing(false);
      await load();
      setNotice({ tone: "success", text: "LHR 扣费配置已保存" });
    } catch (error) {
      setLhrError(error instanceof Error ? error.message : "无法保存 LHR 扣费配置");
    } finally {
      setIsLhrSaving(false);
    }
  };

  const toggleSupplier = async (supplier: SupplierItem) => {
    try {
      await updateSupplier(supplier.id, { status: supplier.status === "active" ? "inactive" : "active" });
      await load();
    } catch (error) {
      setNotice({ tone: "error", text: error instanceof Error ? error.message : "Unable to update supplier" });
    }
  };

  const activeCount = useMemo(() => suppliers.filter((supplier) => supplier.status === "active").length, [suppliers]);

  if (isLoading || !user) {
    return <main className={styles.loadingPage}>Loading supplier configuration...</main>;
  }

  return (
    <AppShell active="suppliers" isInfoOpen={false} messages={[]} onInfoClose={() => undefined} onInfoOpen={() => undefined} onLogout={async () => { await logout(); router.replace("/"); }} unreadCount={0} user={user}>
      <section className={styles.workspace}>
        <header className={styles.header}>
          <div><p>Configuration registry</p><h2>Supplier</h2></div>
          <div className={styles.headerActions}>
            <button className={styles.retroactiveButton} onClick={() => { setIsRetroactiveOpen(true); setRetroactiveResult(null); }} type="button"><History aria-hidden="true" size={17} />Tax backfill</button>
            <button onClick={openNew} type="button"><Plus aria-hidden="true" size={17} />Add supplier</button>
          </div>
        </header>

        {notice && <div className={styles.notice} data-tone={notice.tone} role={notice.tone === "error" ? "alert" : "status"}>{notice.text}</div>}

        <form className={styles.settingsCard} onSubmit={handleSaveSettings}>
          <div className={styles.settingsLead}><Settings2 aria-hidden="true" size={22} /><div><span>Global billing policy</span><strong>Tax amount and eligible arrival airports</strong></div></div>
          <label>Unit tax (EUR)<input inputMode="decimal" min="0" onChange={(event) => setUnitRate(event.target.value)} required step="0.01" type="number" value={unitRate} /></label>
          <label>Taxable IATA airports<input onChange={(event) => setAirportText(event.target.value.toUpperCase())} placeholder="AMS, FRA" value={airportText} /></label>
          <label>Tax effective date<input onChange={(event) => setTaxEffectiveDate(event.target.value)} required type="date" value={taxEffectiveDate} /></label>
          <button type="submit"><Save aria-hidden="true" size={16} />Save policy</button>
        </form>

        <section className={styles.registry}>
          <div className={styles.registryHeader}><div><p>Current suppliers</p><h3>Published configurations</h3></div><span>{activeCount} active / {suppliers.length} total</span></div>
          <div className={styles.supplierGrid}>
            {suppliers.map((supplier) => {
              const config = supplier.currentVersion.config;
              return (
                <article className={styles.supplierCard} data-status={supplier.status} key={supplier.id}>
                  <div className={styles.cardTop}><span className={styles.supplierIcon}><Factory aria-hidden="true" size={20} /></span><span className={styles.status}>{supplier.status}</span></div>
                  <div><h4>{supplier.name}</h4><p>Version {supplier.currentVersionNumber} · {config.fields.length} rules</p></div>
                  <dl><div><dt>Worksheet</dt><dd>{config.workbook.sheetMode === "first" ? "First sheet" : config.workbook.sheetName}</dd></div><div><dt>Waybill column</dt><dd>{billingColumnLabel(config, "group")}</dd></div><div><dt>Carton column</dt><dd>{billingColumnLabel(config, "distinct")}</dd></div><div><dt>Data starts</dt><dd>Row {config.workbook.dataStartRow}</dd></div></dl>
                  <footer><button onClick={() => openEdit(supplier)} type="button">Edit & publish</button><button onClick={() => void toggleSupplier(supplier)} type="button">{supplier.status === "active" ? "Deactivate" : "Activate"}</button></footer>
                </article>
              );
            })}
          </div>
        </section>

        <section className={`${styles.registry} ${styles.lhrRegistry}`} aria-labelledby="lhr-registry-title">
          <div className={styles.registryHeader}><div><p>Destination fees · LHR</p><h3 id="lhr-registry-title">LHR 扣费配置</h3></div><span>一套独立配置 · 仅用于 LHR</span></div>
          <div className={styles.lhrConfigGrid}>
            <article className={styles.lhrConfigCard}>
              <div className={styles.lhrConfigIdentity}><span className={styles.supplierIcon}><Factory aria-hidden="true" size={20} /></span><div><h4>LHR 专用收费</h4><small>独立配置 · {lhrSettings?.version ? `版本 ${lhrSettings.version}` : "尚未创建"}</small></div><span className={styles.lhrConfigStatus} data-configured={Boolean(lhrSettings?.config)}>{lhrSettings?.config ? "已配置" : "未配置"}</span></div>
              <dl><div><dt>清关费</dt><dd>{lhrSettings?.config ? `€${lhrSettings.config.clearanceFeeEur} / 票` : "—"}</dd></div><div><dt>客户报价</dt><dd>{lhrSettings?.config ? `${lhrSettings.config.customerRates.length} 位客户` : "—"}</dd></div><div><dt>货站附加费</dt><dd>{lhrSettings?.config ? `${lhrSettings.config.surchargeRules.length} 条规则` : "—"}</dd></div></dl>
              <button onClick={openLhrEdit} type="button">{lhrSettings?.config ? "管理 LHR 扣费" : "创建 LHR 扣费配置"}</button>
            </article>
          </div>
          {lhrEditing && <form aria-labelledby="lhr-editor-title" className={`${styles.editor} ${styles.lhrInlineEditor}`} onSubmit={handleSaveLhr}>
            <header className={styles.editorHeader}><div><p>Global destination fees · LHR</p><h3 id="lhr-editor-title">LHR 扣费设置</h3></div><button aria-label="关闭 LHR 配置" onClick={() => setLhrEditing(false)} type="button"><X aria-hidden="true" size={18} /></button></header>
            {lhrError && <div className={styles.editorNotice} role="alert">{lhrError}</div>}
            <section className={`${styles.editorSection} ${styles.lhrSection}`} aria-label="LHR billing configuration">
              <div className={styles.sectionTitle}><span>UK</span><div><strong>LHR 独立扣费</strong><small>只使用提单号、提单总重量和所选客户；不读取 Pre Alert 内容计费</small></div></div>
              <label className={styles.lhrToggle}><input checked={Boolean(lhrDraft)} onChange={(event) => setLhrDraft(event.target.checked ? { clearanceFeeEur: "45.00", customerRates: [], surchargeRules: [] } : null)} type="checkbox" />启用 LHR 扣费配置</label>
              {!lhrDraft ? <p className={styles.lhrHint}>未创建收费名单时，LHR 提单仍可上传，且不会扣除 LHR 费用。</p> : <>
                <div className={styles.lhrGroup}>
                  <div className={styles.lhrGroupHead}><div><strong>01 · 清关费</strong><small>按 Air Waybill Number，一次上传计一票</small></div></div>
                  <label className={styles.lhrMoneyField}>每票金额 (EUR)<input min="0.01" onChange={(event) => setLhrBilling((billing) => ({ ...billing, clearanceFeeEur: event.target.value }))} required step="0.01" type="number" value={lhrDraft.clearanceFeeEur} /></label>
                </div>
                <div className={styles.lhrGroup}>
                  <div className={styles.lhrGroupHead}><div><strong>02 · 客户每公斤报价</strong><small>只有加入列表的客户才收取 LHR 清关费、重量费和匹配的货站附加费</small></div><button className={styles.addRule} onClick={() => { setCustomerDialog({ userId: "", rate: "", editing: false }); setCustomerDialogError(null); }} type="button"><Plus size={15} />添加客户</button></div>
                  {lhrDraft.customerRates.length ? <div className={styles.customerRateList}>{lhrDraft.customerRates.map((rate) => {
                    const customer = customers.find((item) => item.id === rate.userId);
                    return <div className={styles.customerRateRow} key={rate.userId}><div><strong>{customer?.username || "已删除客户"}</strong><small>{customer?.email || rate.userId}</small></div><b>£{rate.rateGbpPerKg} / kg</b><button onClick={() => { setCustomerDialog({ userId: rate.userId, rate: rate.rateGbpPerKg, editing: true }); setCustomerDialogError(null); }} type="button">修改</button><button aria-label={`删除 ${customer?.username || rate.userId} 报价`} onClick={() => setLhrBilling((billing) => ({ ...billing, customerRates: billing.customerRates.filter((item) => item.userId !== rate.userId) }))} type="button"><X size={15} /></button></div>;
                  })}</div> : <p className={styles.lhrHint}>尚无收费客户；所有客户仍可上传 LHR 提单，且不扣除 LHR 费用。</p>}
                </div>
                <div className={styles.lhrGroup}>
                  <div className={styles.lhrGroupHead}><div><strong>03 · 货站附加费</strong><small>同一三位提单前缀只能归属一条规则；未匹配时不收附加费</small></div><div className={styles.lhrActions}><button className={styles.addRule} onClick={() => addSurchargeRule("fixed")} type="button"><Plus size={15} />固定金额</button><button className={styles.addRule} onClick={() => addSurchargeRule("weight_bands")} type="button"><Plus size={15} />重量段</button></div></div>
                  {lhrDraft.surchargeRules.length ? <div className={styles.surchargeList}>{lhrDraft.surchargeRules.map((rule, index) => <article className={styles.surchargeCard} key={`surcharge-${index}`}>
                    <div className={styles.surchargeTitle}><strong>{rule.mode === "fixed" ? "固定金额规则" : "重量段规则"} #{index + 1}</strong><button aria-label={`删除货站规则 ${index + 1}`} onClick={() => setLhrBilling((billing) => ({ ...billing, surchargeRules: billing.surchargeRules.filter((_, i) => i !== index) }))} type="button"><X size={16} /></button></div>
                    <div className={styles.surchargeFields}><label>规则名称<input onChange={(event) => updateSurchargeRule(index, (current) => ({ ...current, name: event.target.value }))} placeholder="如 Swissport" required value={rule.name} /></label><label>提单前三位（逗号分隔）<input onChange={(event) => updateSurchargeRule(index, (current) => ({ ...current, prefixes: event.target.value.split(/[,，\s&]+/).map((value) => value.trim()).filter(Boolean) }))} pattern=".*" placeholder="016, 180, 105" required value={rule.prefixes.join(", ")} /></label>{rule.mode === "fixed" && <label>每票附加费 (GBP)<input min="0.01" onChange={(event) => updateSurchargeRule(index, (current) => ({ ...current, amountGbp: event.target.value }))} required step="0.01" type="number" value={rule.amountGbp || ""} /></label>}</div>
                    {rule.mode === "weight_bands" && <div className={styles.bandList}><p>重量段按提单重量向上取整到整公斤后匹配；首档从 0 开始，各档须连续，最后一档上限留空。</p>{rule.bands.map((band, bandIndex) => <div className={styles.bandRow} key={bandIndex}><label>起始 kg<input min="0" onChange={(event) => updateSurchargeRule(index, (current) => ({ ...current, bands: current.bands.map((item, i) => i === bandIndex ? { ...item, minWeightKg: Number(event.target.value) } : item) }))} required step="1" type="number" value={band.minWeightKg} /></label><label>结束 kg<input min={band.minWeightKg} onChange={(event) => updateSurchargeRule(index, (current) => ({ ...current, bands: current.bands.map((item, i) => i === bandIndex ? { ...item, maxWeightKg: event.target.value === "" ? null : Number(event.target.value) } : item) }))} placeholder="无上限" step="1" type="number" value={band.maxWeightKg ?? ""} /></label><label>附加费 (GBP)<input min="0.01" onChange={(event) => updateSurchargeRule(index, (current) => ({ ...current, bands: current.bands.map((item, i) => i === bandIndex ? { ...item, amountGbp: event.target.value } : item) }))} required step="0.01" type="number" value={band.amountGbp} /></label><button aria-label={`删除重量段 ${bandIndex + 1}`} disabled={rule.bands.length === 1} onClick={() => updateSurchargeRule(index, (current) => ({ ...current, bands: current.bands.filter((_, i) => i !== bandIndex) }))} type="button"><X size={15} /></button></div>)}<button className={styles.addRule} disabled={rule.bands[rule.bands.length - 1]?.maxWeightKg == null} onClick={() => updateSurchargeRule(index, (current) => ({ ...current, bands: [...current.bands, { minWeightKg: (current.bands[current.bands.length - 1].maxWeightKg ?? 0) + 1, maxWeightKg: null, amountGbp: "" }] }))} type="button"><Plus size={15} />添加重量段</button></div>}
                  </article>)}</div> : <p className={styles.lhrHint}>无货站附加费规则时，只收清关费和客户公斤费。</p>}
                </div>
              </>}
            </section>
            <footer className={styles.editorFooter}><span>此配置只用于目的港 LHR，保存后立即用于新的预估与上传。</span><div><button onClick={() => setLhrEditing(false)} type="button">取消</button><button disabled={isLhrSaving || (!lhrDraft && !lhrSettings?.config)} type="submit"><Save size={16} />{isLhrSaving ? "正在保存..." : "保存 LHR 扣费"}</button></div></footer>
          </form>}
        </section>
      </section>

      {editing && (
        <div className={styles.backdrop} role="presentation">
          <form aria-labelledby="supplier-editor-title" aria-modal="true" className={styles.editor} onSubmit={handleSaveSupplier} role="dialog">
            <header className={styles.editorHeader}><div><p>{editing === "new" ? "New configuration" : `Publishing version ${editing.currentVersionNumber + 1}`}</p><h3 id="supplier-editor-title">{editing === "new" ? "Add supplier" : `Edit ${editing.name}`}</h3></div><button aria-label="Close supplier editor" onClick={() => setEditing(null)} type="button"><X aria-hidden="true" size={18} /></button></header>
            {notice?.tone === "error" && <div className={styles.editorNotice} role="alert">{notice.text}</div>}

            <section className={styles.editorSection}><div className={styles.sectionTitle}><span>01</span><div><strong>Supplier information</strong><small>Identity and workbook layout</small></div></div><div className={styles.editorGrid}>
              <label>Supplier name<input onChange={(event) => setDraftName(event.target.value)} required value={draftName} /></label>
              <label>Worksheet<select onChange={(event) => setDraftConfig((current) => ({ ...current, workbook: { ...current.workbook, sheetMode: event.target.value as "first" | "named" } }))} value={draftConfig.workbook.sheetMode}><option value="first">First worksheet</option><option value="named">Named worksheet</option></select></label>
              {draftConfig.workbook.sheetMode === "named" && <label>Worksheet name<input onChange={(event) => setDraftConfig((current) => ({ ...current, workbook: { ...current.workbook, sheetName: event.target.value } }))} required value={draftConfig.workbook.sheetName || ""} /></label>}
              <label>Header row<input min="1" onChange={(event) => setDraftConfig((current) => ({ ...current, workbook: { ...current.workbook, headerRow: Number(event.target.value) } }))} required type="number" value={draftConfig.workbook.headerRow} /></label>
              <label>Data starts at row<input min="2" onChange={(event) => setDraftConfig((current) => ({ ...current, workbook: { ...current.workbook, dataStartRow: Number(event.target.value) } }))} required type="number" value={draftConfig.workbook.dataStartRow} /></label>
            </div></section>

            <section className={styles.editorSection}><div className={styles.sectionTitle}><span>02</span><div><strong>Pre Alert field rules</strong><small>Safe, structured validation — no executable formulas</small></div><button className={styles.addRule} onClick={() => setDraftConfig((current) => ({ ...current, fields: [...current.fields, newRule(current.fields.length)] }))} type="button"><Plus size={15} />Add rule</button></div><div className={styles.rules}>
              {draftConfig.fields.map((rule, index) => (
                <article className={styles.ruleCard} key={rule.key}>
                  <div className={styles.ruleHeader}><strong>Rule {index + 1}</strong><button aria-label={`Remove rule ${index + 1}`} disabled={draftConfig.fields.length === 1} onClick={() => removeRule(index)} type="button"><X size={15} /></button></div>
                  <div className={styles.ruleGrid}>
                    <label>Rule name<input onChange={(event) => updateRule(index, (current) => ({ ...current, name: event.target.value }))} required value={rule.name} /></label>
                    <label>System use<select onChange={(event) => updateRule(index, (current) => ({ ...current, semanticField: (event.target.value || null) as SupplierSemanticField | null }))} value={rule.semanticField || ""}><option value="">Custom validation</option><option value="parcel_unit_number">Parcel Unit Number</option><option value="destination">Destination</option><option value="number_of_items">Number of Items</option><option value="weight_kg">Weight KG</option></select></label>
                    <label>Locate by<select onChange={(event) => updateRule(index, (current) => ({ ...current, locatorMode: event.target.value as "column" | "header" }))} value={rule.locatorMode}><option value="column">Excel column</option><option value="header">Header name</option></select></label>
                    <label>{rule.locatorMode === "column" ? "Column" : "Header"}<input onChange={(event) => updateRule(index, (current) => ({ ...current, locatorValue: rule.locatorMode === "column" ? event.target.value.toUpperCase() : event.target.value }))} required value={rule.locatorValue} /></label>
                    <label>Value type<select onChange={(event) => updateRule(index, (current) => ({ ...current, valueType: event.target.value as SupplierFieldRule["valueType"] }))} value={rule.valueType}><option value="text">Text</option><option value="number">Number</option><option value="integer">Integer</option><option value="country">Country</option></select></label>
                    <label>Blank handling<select onChange={(event) => updateRule(index, (current) => ({ ...current, blankPolicy: event.target.value as SupplierFieldRule["blankPolicy"] }))} value={rule.blankPolicy}><option value="allow">Allow blank</option><option value="required">Warn when blank</option><option value="skip_row">Skip entire row</option></select></label>
                    <label>Minimum<input onChange={(event) => updateRule(index, (current) => ({ ...current, constraints: { ...current.constraints, minValue: event.target.value || null } }))} type="number" value={rule.constraints.minValue || ""} /></label>
                    <label>Maximum<input onChange={(event) => updateRule(index, (current) => ({ ...current, constraints: { ...current.constraints, maxValue: event.target.value || null } }))} type="number" value={rule.constraints.maxValue || ""} /></label>
                    <label>Minimum length<input min="0" onChange={(event) => updateRule(index, (current) => ({ ...current, constraints: { ...current.constraints, minLength: event.target.value ? Number(event.target.value) : null } }))} type="number" value={rule.constraints.minLength ?? ""} /></label>
                    <label>Maximum length<input min="0" onChange={(event) => updateRule(index, (current) => ({ ...current, constraints: { ...current.constraints, maxLength: event.target.value ? Number(event.target.value) : null } }))} type="number" value={rule.constraints.maxLength ?? ""} /></label>
                    <label>Regex pattern<input onChange={(event) => updateRule(index, (current) => ({ ...current, constraints: { ...current.constraints, pattern: event.target.value || null } }))} value={rule.constraints.pattern || ""} /></label>
                    <label>Allowed values<input onChange={(event) => updateRule(index, (current) => ({ ...current, constraints: { ...current.constraints, allowedValues: event.target.value.split(",").map((value) => value.trim()).filter(Boolean) } }))} placeholder="A, B, C" value={rule.constraints.allowedValues.join(", ")} /></label>
                    {rule.valueType === "country" && <label>Country aliases<input onChange={(event) => updateRule(index, (current) => ({ ...current, countryAliases: Object.fromEntries(event.target.value.split(",").map((pair) => pair.split("=").map((value) => value.trim())).filter((pair) => pair.length === 2 && pair[0] && pair[1])) }))} placeholder="Deutschland=DE" value={Object.entries(rule.countryAliases).map(([source, code]) => `${source}=${code}`).join(", ")} /></label>}
                  </div>
                  <div className={styles.ruleOptions}><label><input checked={rule.caseInsensitive} onChange={(event) => updateRule(index, (current) => ({ ...current, caseInsensitive: event.target.checked }))} type="checkbox" />Ignore case</label><label><input checked={rule.constraints.unique} onChange={(event) => updateRule(index, (current) => ({ ...current, constraints: { ...current.constraints, unique: event.target.checked } }))} type="checkbox" />Warn on duplicates</label>{rule.valueType === "country" && <label><input checked={rule.allowUnknownCountry} onChange={(event) => updateRule(index, (current) => ({ ...current, allowUnknownCountry: event.target.checked }))} type="checkbox" />Allow unknown countries</label>}</div>
                  <code>{formula(rule)}</code>
                </article>
              ))}
            </div></section>

            <section className={styles.editorSection}><div className={styles.sectionTitle}><span>03</span><div><strong>Deduction logic</strong><small>Independent Excel columns; not linked to Pre Alert field rules</small></div></div><div className={styles.editorGrid}>
              <label>Waybill number column<input autoCapitalize="characters" maxLength={3} onChange={(event) => setDraftConfig((current) => ({ ...current, billingGroupColumn: event.target.value.toUpperCase() }))} pattern="[A-Za-z]{1,3}" placeholder="C" required value={draftConfig.billingGroupColumn || ""} /></label>
              <label>Carton number column<input autoCapitalize="characters" maxLength={3} onChange={(event) => setDraftConfig((current) => ({ ...current, billingDistinctColumn: event.target.value.toUpperCase() }))} pattern="[A-Za-z]{1,3}" placeholder="X" required value={draftConfig.billingDistinctColumn || ""} /></label>
              <div className={styles.logicSummary}><CheckCircle2 size={18} /><span>Each waybill contributes at least one carton. Repeated rows count the distinct carton values within that waybill only; cartons are never merged across different waybills.</span></div>
            </div></section>
            <footer className={styles.editorFooter}><span><AlertTriangle size={16} />Rule violations become review warnings; workbook structure errors block uploads.</span><div><button onClick={() => setEditing(null)} type="button">Cancel</button><button disabled={isSaving} type="submit"><FileSpreadsheet size={16} />{isSaving ? "Publishing..." : editing === "new" ? "Create supplier" : "Publish new version"}</button></div></footer>
          </form>
        </div>
      )}

      {customerDialog && <div className={`${styles.backdrop} ${styles.customerBackdrop}`} role="presentation"><div aria-labelledby="customer-rate-title" aria-modal="true" className={styles.customerModal} role="dialog"><header><div><small>LHR pricing</small><h3 id="customer-rate-title">{customerDialog.editing ? "修改客户报价" : "添加客户报价"}</h3></div><button aria-label="关闭客户报价" onClick={() => setCustomerDialog(null)} type="button"><X size={18} /></button></header><div className={styles.customerModalBody}><label>客户<select disabled={customerDialog.editing} onChange={(event) => setCustomerDialog((current) => current ? { ...current, userId: event.target.value } : null)} value={customerDialog.userId}><option value="">选择客户</option>{customers.filter((item) => item.status === "active" && item.role === "user" && (customerDialog.editing || !lhrDraft?.customerRates.some((rate) => rate.userId === item.id))).map((item) => <option key={item.id} value={item.id}>{item.username} · {item.email}</option>)}</select></label><label>每公斤报价 (GBP)<input inputMode="decimal" min="0.01" onChange={(event) => setCustomerDialog((current) => current ? { ...current, rate: event.target.value } : null)} placeholder="0.50" step="0.01" type="number" value={customerDialog.rate} /></label>{customerDialogError && <p role="alert">{customerDialogError}</p>}</div><footer><button onClick={() => setCustomerDialog(null)} type="button">取消</button><button onClick={confirmCustomerRate} type="button">确认</button></footer></div></div>}

      {isRetroactiveOpen && (
        <div className={styles.backdrop} role="presentation">
          <form aria-labelledby="retroactive-title" aria-modal="true" className={`${styles.editor} ${styles.retroactiveEditor}`} onSubmit={handleRetroactiveBilling} role="dialog">
            <header className={styles.editorHeader}>
              <div><p>Legacy customs reconciliation</p><h3 id="retroactive-title">Tax backfill</h3></div>
              <button aria-label="Close tax backfill" onClick={() => setIsRetroactiveOpen(false)} type="button"><X aria-hidden="true" size={18} /></button>
            </header>
            <section className={styles.retroactiveIntro}>
              <span><CircleDollarSign aria-hidden="true" size={24} /></span>
              <div><strong>Process historical waybills one by one</strong><p>Every Pre Alert file is tried against the current active supplier formats. Successful deductions may make the customer balance negative.</p></div>
            </section>
            <section className={styles.retroactiveBody}>
              <label>Waybill numbers
                <textarea aria-label="Waybill numbers" onChange={(event) => setRetroactiveText(event.target.value)} placeholder="784-84063276 020-12345678&#10;Separate numbers with spaces or new lines" required value={retroactiveText} />
              </label>
              <div className={styles.cutoffNote}><History aria-hidden="true" size={17} /><span>Only approved uploads dated on or after <strong>{taxEffectiveDate}</strong> and arriving at {airportText || "a configured airport"} are eligible.</span></div>
            </section>
            {retroactiveResult && (
              <section className={styles.retroactiveResults}>
                <div className={styles.resultSummary}>
                  <div><span>Requested</span><strong>{retroactiveResult.requestedCount}</strong></div>
                  <div data-tone="success"><span>Recorded</span><strong>{retroactiveResult.succeededCount}</strong></div>
                  <div data-tone="error"><span>Failed</span><strong>{retroactiveResult.failedCount}</strong></div>
                </div>
                {retroactiveResult.succeeded.length > 0 && <div className={styles.resultGroup}><h4>Recorded deductions</h4>{retroactiveResult.succeeded.map((item) => <div className={styles.resultRow} key={item.waybillNumber}><div><strong>{item.waybillNumber}</strong><span>{item.supplierName} v{item.supplierVersionNumber}</span></div><span>{item.billableUnitCount} cartons × €{item.unitRate}</span><strong>€{item.amount}</strong></div>)}</div>}
                {retroactiveResult.failed.length > 0 && <div className={`${styles.resultGroup} ${styles.failureGroup}`}><h4>Failed waybills</h4>{retroactiveResult.failed.map((item) => <div className={styles.failureRow} key={item.waybillNumber}><strong>{item.waybillNumber}</strong><span>{item.reason}</span></div>)}</div>}
              </section>
            )}
            <footer className={styles.editorFooter}><span><AlertTriangle size={16} />Already billed waybills are rejected to prevent duplicate deductions.</span><div><button onClick={() => setIsRetroactiveOpen(false)} type="button">Close</button><button disabled={isProcessingRetroactive} type="submit"><CircleDollarSign size={16} />{isProcessingRetroactive ? "Processing..." : "Process backfill"}</button></div></footer>
          </form>
        </div>
      )}
    </AppShell>
  );
}
