/* Built-in CSP Spider implementations for common csp_XXX classes */
/* Each spider must implement: homeContent, categoryContent, detailContent, searchContent, playerContent */

(function() {
    var CspRegistry = {};

    /* ========== Generic HTTP API Spider ========== */
    /* Used when ext contains a direct API URL */
    function createGenericSpider(ext) {
        var apiUrl = '';
        if (typeof ext === 'string' && ext.startsWith('http')) {
            apiUrl = ext;
        } else if (typeof ext === 'string' && ext.startsWith('{')) {
            try {
                var obj = JSON.parse(ext);
                apiUrl = obj.url || obj.host || '';
                if (obj.site && obj.site.length > 0) {
                    apiUrl = obj.site[0];
                }
            } catch(e) {}
        } else if (typeof ext === 'object' && ext !== null) {
            apiUrl = ext.url || ext.host || '';
            if (ext.site && ext.site.length > 0) {
                apiUrl = ext.site[0];
            }
        }
        return {
            homeContent: function(filter) {
                if (!apiUrl) return {class: [], list: []};
                try {
                    var resp = req(apiUrl);
                    var data = JSON.parse(resp);
                    return data;
                } catch(e) {
                    return {class: [], list: []};
                }
            },
            categoryContent: function(tid, pg, filter, extend) {
                if (!apiUrl) return {list: []};
                try {
                    var url = apiUrl + '?ac=videolist&t=' + tid + '&pg=' + pg;
                    if (extend) {
                        for (var k in extend) {
                            url += '&' + k + '=' + encodeURIComponent(extend[k]);
                        }
                    }
                    var resp = req(url);
                    var data = JSON.parse(resp);
                    return data;
                } catch(e) {
                    return {list: []};
                }
            },
            detailContent: function(ids) {
                if (!apiUrl) return {list: []};
                try {
                    var id = Array.isArray(ids) ? ids.join(',') : ids;
                    var url = apiUrl + '?ac=detail&ids=' + encodeURIComponent(id);
                    var resp = req(url);
                    var data = JSON.parse(resp);
                    return data;
                } catch(e) {
                    return {list: []};
                }
            },
            searchContent: function(key, quick, pg) {
                if (!apiUrl) return {list: []};
                try {
                    var url = apiUrl + '?wd=' + encodeURIComponent(key) + '&pg=' + (pg || '1');
                    var resp = req(url);
                    var data = JSON.parse(resp);
                    return data;
                } catch(e) {
                    return {list: []};
                }
            },
            playerContent: function(flag, id, vipFlags) {
                return {parse: 0, url: id, flag: flag};
            }
        };
    }

    /* ========== csp_Bili - Bilibili Spider ========== */
    CspRegistry.Bili = {
        searchContent: function(key, quick, pg) {
            try {
                var url = 'https://search.bilibili.com/api/search?search_type=video&keyword=' + encodeURIComponent(key) + '&page=' + (pg || 1);
                var resp = req(url);
                var data = JSON.parse(resp);
                var list = [];
                if (data && data.data && data.data.result) {
                    for (var i = 0; i < data.data.result.length; i++) {
                        var v = data.data.result[i];
                        list.push({
                            vod_id: 'bili:' + v.aid,
                            vod_name: v.title,
                            vod_pic: v.pic,
                            vod_remarks: v.duration,
                            vod_year: '',
                            vod_area: ''
                        });
                    }
                }
                return {list: list};
            } catch(e) {
                return {list: []};
            }
        },
        homeContent: function(filter) { return {class: [], list: []}; },
        categoryContent: function(tid, pg, filter, extend) { return {list: []}; },
        detailContent: function(ids) { return {list: []}; },
        playerContent: function(flag, id, vipFlags) { return {parse: 0, url: id, flag: flag}; }
    };

    /* ========== csp_Douban - Douban Spider ========== */
    CspRegistry.Douban = {
        searchContent: function(key, quick, pg) {
            try {
                var url = 'https://movie.douban.com/j/subject_suggest?q=' + encodeURIComponent(key);
                var resp = req(url, {headers: {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://movie.douban.com/'}});
                var data = JSON.parse(resp);
                var list = [];
                for (var i = 0; i < data.length; i++) {
                    var v = data[i];
                    list.push({
                        vod_id: 'douban:' + v.id,
                        vod_name: v.title,
                        vod_pic: v.img || v.pic || '',
                        vod_remarks: v.year || '',
                        vod_year: v.year || '',
                        vod_area: ''
                    });
                }
                return {list: list};
            } catch(e) {
                return {list: []};
            }
        },
        homeContent: function(filter) { return {class: [], list: []}; },
        categoryContent: function(tid, pg, filter, extend) { return {list: []}; },
        detailContent: function(ids) { return {list: []}; },
        playerContent: function(flag, id, vipFlags) { return {parse: 0, url: id, flag: flag}; }
    };

    /* ========== csp_4KZhinan - 4K Guide Spider ========== */
    CspRegistry['4KZhinan'] = {
        searchContent: function(key, quick, pg) {
            try {
                var url = 'https://www.4kzhinan.cn/api/search?keyword=' + encodeURIComponent(key);
                var resp = req(url);
                var data = JSON.parse(resp);
                return data;
            } catch(e) {
                return {list: []};
            }
        },
        homeContent: function(filter) { return {class: [], list: []}; },
        categoryContent: function(tid, pg, filter, extend) { return {list: []}; },
        detailContent: function(ids) { return {list: []}; },
        playerContent: function(flag, id, vipFlags) { return {parse: 0, url: id, flag: flag}; }
    };

    /* ========== csp_RenRen - RenRen Spider ========== */
    CspRegistry.RenRen = {
        searchContent: function(key, quick, pg) {
            try {
                var url = 'https://www.rrys2020.com/search?keyword=' + encodeURIComponent(key);
                var resp = req(url, {headers: {'User-Agent': 'Mozilla/5.0'}});
                var html = resp;
                var list = [];
                var pattern = /<a[^>]*href="\/resource\/(\d+)"[^>]*>([^<]+)<\/a>/g;
                var match;
                while ((match = pattern.exec(html)) !== null) {
                    list.push({
                        vod_id: 'renren:' + match[1],
                        vod_name: match[2].trim(),
                        vod_pic: '',
                        vod_remarks: ''
                    });
                }
                return {list: list};
            } catch(e) {
                return {list: []};
            }
        },
        homeContent: function(filter) { return {class: [], list: []}; },
        categoryContent: function(tid, pg, filter, extend) { return {list: []}; },
        detailContent: function(ids) { return {list: []}; },
        playerContent: function(flag, id, vipFlags) { return {parse: 0, url: id, flag: flag}; }
    };

    /* ========== Default generic spider for unknown csp_XXX ========== */
    function getDefaultSpider() {
        return {
            homeContent: function(filter) { return {class: [], list: []}; },
            categoryContent: function(tid, pg, filter, extend) { return {list: []}; },
            detailContent: function(ids) { return {list: []}; },
            searchContent: function(key, quick, pg) { return {list: []}; },
            playerContent: function(flag, id, vipFlags) { return {parse: 0, url: id, flag: flag}; }
        };
    }

    /* ========== Factory ========== */
    function getSpider(className, ext) {
        var name = className;
        if (name.startsWith('csp_')) name = name.substring(4);

        if (CspRegistry[name]) {
            return CspRegistry[name];
        }

        /* Try generic spider with ext */
        if (ext) {
            var generic = createGenericSpider(ext);
            if (generic.apiUrl) return generic;
        }

        return getDefaultSpider();
    }

    /* Export */
    this.CspRegistry = CspRegistry;
    this.getSpider = getSpider;
    this.loadCspSpider = function(className, ext) {
        var spider = getSpider(className, ext);
        if (spider) {
            this.homeContent = function(filter) { return JSON.stringify(spider.homeContent(filter)); };
            this.categoryContent = function(tid, pg, filter, extend) { return JSON.stringify(spider.categoryContent(tid, pg, filter, extend)); };
            this.detailContent = function(ids) { return JSON.stringify(spider.detailContent(ids)); };
            this.searchContent = function(key, quick, pg) { return JSON.stringify(spider.searchContent(key, quick, pg)); };
            this.playerContent = function(flag, id, vipFlags) { return JSON.stringify(spider.playerContent(flag, id, vipFlags)); };
            this.liveContent = function(url) { return JSON.stringify(spider.liveContent ? spider.liveContent(url) : ''); };
            return true;
        }
        return false;
    };
})();