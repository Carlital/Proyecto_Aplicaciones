/** @odoo-module **/
import publicWidget from "@web/legacy/js/public/public_widget";
import { jsonrpc } from "@web/core/network/rpc_service";

publicWidget.registry.DocenteSnippet = publicWidget.Widget.extend({
    selector: '.s_banner[data-name="Lista Docentes"]',
    events: {
        'click #btn-filtrar': '_onFiltrar',
        'keyup #busqueda_docente': '_onFiltrar',
        'change #filtro_carrera': '_onFiltrar',
        'click .docente-page': '_onPaginate',
    },

    start: function () {
        this.currentPage = 1;
        this._onFiltrar();
        return this._super.apply(this, arguments);
    },

    _onPaginate: function (ev) {
        ev.preventDefault();
        this.currentPage = parseInt($(ev.currentTarget).data('page'));
        this._onFiltrar(ev);
    },
    
    _onFiltrar: function (ev = null) {
        const self = this;
        const carrera_id = this.$('#filtro_carrera').val();
        const nombre = this.$('#busqueda_docente').val();

        if (!ev || ev.type !== 'click' || !$(ev.currentTarget).hasClass('docente-page')) {
            this.currentPage = 1;
        }

        jsonrpc('/docente_snippet/filtro_docentes', {
            carrera_id: carrera_id || null,
            nombre: nombre || null,
            page: this.currentPage,
            limit: 10
        }).then(function (result) {
            self.$('#lista-docentes').html(result.html);
            self.$('#pagination-docentes').html(result.pagination);
        }).catch(function (err) {
            console.error("[DocenteSnippet] Error:", err);
        });
    }
});
