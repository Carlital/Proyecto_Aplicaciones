/** @odoo-module **/

import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

const cvImporterBusService = {
    dependencies: ["bus_service", "notification"],

    start(env, { bus_service, notification }) {
        if (!bus_service) {
            console.warn(
                "cv_importer: bus_service no está disponible."
            );
            return;
        }
        if (!notification) {
            console.warn("cv_importer: notification service no está disponible.");
            return;
        }

        // 🔹 CAMBIO CLAVE: Usar addChannel en lugar de subscribe
        bus_service.addChannel("cv_importer_done");
        
        // 🔹 Escuchar notificaciones del canal
        bus_service.addEventListener("notification", ({ detail: notifications }) => {
            for (const { type, payload } of notifications) {
                if (type === "cv_importer_done") {
                    console.log("✅ cv_importer: Notificación recibida:", payload);
                    
                    const state = payload.state || "info";
                    const mode = payload.mode || "single";
                    const isLast = payload.is_last !== false;
                    const message = payload.message || _t("Importación de CV actualizada.");

                    // En modo lote solo mostrar cuando sea el último
                    if (mode === "batch" && !isLast) {
                        console.log("⏭️ Modo lote, esperando último registro...");
                        continue;
                    }

                    let notifType = "info";
                    if (state === "processed") {
                        notifType = "success";
                    } else if (state === "error") {
                        notifType = "danger";
                    } else if (state === "processing") {
                        notifType = "warning";
                    }

                    const params = {
                        title: _t("Importación de CV"),
                        message,
                        type: notifType,
                        sticky: false,
                    };

                    // 🔹 Imports individuales -> recargar vista al cerrar
                    if (mode === "single") {
                        params.sticky = true;

                        window.__cvImporterReloadDone = false;

                        params.buttons = [
                            {
                                name: _t("Aceptar"),
                                primary: true,
                                onClick: () => {
                                    window.__cvImporterReloadDone = true;
                                    window.location.reload();
                                },
                            },
                        ];

                        setTimeout(() => {
                            if (!window.__cvImporterReloadDone) {
                                window.__cvImporterReloadDone = true;
                                window.location.reload();
                            }
                        }, 60000);
                    }

                    notification.add(params.message, {
                        title: params.title,
                        type: params.type,
                        sticky: params.sticky,
                        buttons: params.buttons || [],
                    });

                    console.log("🔔 Notificación mostrada:", params);
                }
            }
        });

        console.log("✅ cv_importer_bus_listener inicializado correctamente");
    },
};

registry.category("services").add(
    "cv_importer_bus_listener",
    cvImporterBusService
);