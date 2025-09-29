/**
 * Formateador automático para el contenido de la pestaña Docencia
 * Organiza el texto en secciones estructuradas
 */

document.addEventListener('DOMContentLoaded', function() {
    formatDocenciaContent();
});

function formatDocenciaContent() {
    const docenciaContent = document.querySelector('.teaching-content .info-formateada');
    if (!docenciaContent) return;

    const originalText = docenciaContent.innerHTML;
    const formattedHTML = processDocenciaText(originalText);
    docenciaContent.innerHTML = formattedHTML;
}

function processDocenciaText(text) {
    // Limpiar el texto y convertir <br/> a saltos de línea
    let cleanText = text.replace(/<br\s*\/?>/gi, '\n')
                       .replace(/&lt;/g, '<')
                       .replace(/&gt;/g, '>')
                       .replace(/&amp;/g, '&');
    
    const sections = [];
    
    // Detectar y procesar secciones
    const sectionPatterns = [
        {
            name: 'Asignaturas Impartidas',
            icon: 'fa-book',
            keywords: ['ASIGNATURAS IMPARTIDAS', 'MATERIAS', 'CÁTEDRAS'],
            endKeywords: ['MODALIDADES', 'NIVELES', 'CERTIFICACIONES']
        },
        {
            name: 'Modalidades y Niveles',
            icon: 'fa-graduation-cap',
            keywords: ['MODALIDADES', 'NIVELES'],
            endKeywords: ['CERTIFICACIONES', 'LOGROS', 'RECONOCIMIENTOS']
        },
        {
            name: 'Certificaciones y Capacitaciones',
            icon: 'fa-certificate',
            keywords: ['CERTIFICACIONES', 'CAPACITACIONES', 'CURSOS'],
            endKeywords: ['LOGROS', 'RECONOCIMIENTOS', 'PUBLICACIONES']
        },
        {
            name: 'Logros y Reconocimientos',
            icon: 'fa-trophy',
            keywords: ['LOGROS', 'RECONOCIMIENTOS', 'PREMIOS', 'DISTINCIONES'],
            endKeywords: []
        }
    ];

    let remainingText = cleanText;

    sectionPatterns.forEach(pattern => {
        const sectionData = extractSection(remainingText, pattern);
        if (sectionData.content) {
            sections.push({
                title: pattern.name,
                icon: pattern.icon,
                content: sectionData.content,
                type: getSectionType(pattern.name)
            });
            remainingText = sectionData.remaining;
        }
    });

    // Si queda texto sin categorizar, añadirlo como "Información Adicional"
    if (remainingText.trim()) {
        sections.push({
            title: 'Información Adicional',
            icon: 'fa-info-circle',
            content: remainingText.trim(),
            type: 'general'
        });
    }

    return generateSectionsHTML(sections);
}

function extractSection(text, pattern) {
    const startRegex = new RegExp(`(${pattern.keywords.join('|')})`, 'i');
    const startMatch = text.match(startRegex);
    
    if (!startMatch) {
        return { content: '', remaining: text };
    }

    const startIndex = startMatch.index;
    let endIndex = text.length;

    // Buscar el final de la sección
    if (pattern.endKeywords.length > 0) {
        const endRegex = new RegExp(`(${pattern.endKeywords.join('|')})`, 'i');
        const endMatch = text.slice(startIndex).match(endRegex);
        if (endMatch) {
            endIndex = startIndex + endMatch.index;
        }
    }

    const sectionContent = text.slice(startIndex, endIndex).trim();
    const remaining = text.slice(0, startIndex) + text.slice(endIndex);

    return {
        content: sectionContent,
        remaining: remaining
    };
}

function getSectionType(sectionName) {
    if (sectionName.includes('Asignaturas')) return 'subjects';
    if (sectionName.includes('Modalidades')) return 'modalities';
    if (sectionName.includes('Certificaciones')) return 'certifications';
    if (sectionName.includes('Logros')) return 'achievements';
    return 'general';
}

function generateSectionsHTML(sections) {
    if (sections.length === 0) {
        return '<p>No se pudo procesar el contenido de docencia.</p>';
    }

    let html = '';

    sections.forEach(section => {
        html += `
            <div class="docencia-section">
                <div class="docencia-section-header">
                    <i class="fa ${section.icon}"></i>
                    ${section.title}
                </div>
                <div class="docencia-section-content">
                    ${formatSectionContent(section.content, section.type)}
                </div>
            </div>
        `;
    });

    return html;
}

function formatSectionContent(content, type) {
    switch (type) {
        case 'subjects':
            return formatSubjects(content);
        case 'modalities':
            return formatModalities(content);
        case 'certifications':
            return formatCertifications(content);
        case 'achievements':
            return formatAchievements(content);
        default:
            return formatGeneral(content);
    }
}

function formatSubjects(content) {
    const subjects = content.split(/[•\-\n]/)
                           .filter(item => item.trim() && !item.match(/^(ASIGNATURAS|IMPARTIDAS)/i))
                           .map(item => item.trim());
    
    if (subjects.length === 0) return '<p>No se encontraron asignaturas.</p>';
    
    let html = '<ul>';
    subjects.forEach(subject => {
        if (subject) {
            html += `<li>${subject}</li>`;
        }
    });
    html += '</ul>';
    
    return html;
}

function formatModalities(content) {
    const modalidades = content.match(/MODALIDADES:\s*([^N]*)/i);
    const niveles = content.match(/NIVELES:\s*([^C]*)/i);
    
    let html = '<div class="modalidades-niveles">';
    
    if (modalidades) {
        html += `<div class="modalidad-item">
                    <strong>Modalidades:</strong><br>
                    ${modalidades[1].trim()}
                 </div>`;
    }
    
    if (niveles) {
        html += `<div class="nivel-item">
                    <strong>Niveles:</strong><br>
                    ${niveles[1].trim()}
                 </div>`;
    }
    
    html += '</div>';
    return html;
}

function formatCertifications(content) {
    const certifications = content.split(/[•\-\n]/)
                                 .filter(item => item.trim() && !item.match(/^(CERTIFICACIONES|CAPACITACIONES)/i))
                                 .map(item => item.trim());
    
    if (certifications.length === 0) return '<p>No se encontraron certificaciones.</p>';
    
    let html = '<div class="certificaciones-grid">';
    certifications.forEach(cert => {
        if (cert) {
            html += `<div class="certificacion-item">${cert}</div>`;
        }
    });
    html += '</div>';
    
    return html;
}

function formatAchievements(content) {
    const achievements = content.split(/[•\-\n]/)
                               .filter(item => item.trim() && !item.match(/^(LOGROS|RECONOCIMIENTOS)/i))
                               .map(item => item.trim());
    
    if (achievements.length === 0) return '<p>No se encontraron logros.</p>';
    
    let html = '<div class="logros-timeline">';
    achievements.forEach(achievement => {
        if (achievement) {
            const tipo = achievement.includes('ACADÉMICO') ? 'ACADÉMICO' : 'PROFESIONAL';
            html += `
                <div class="logro-item">
                    <span class="logro-tipo">${tipo}</span>
                    <p>${achievement.replace(/\(ACADÉMICO\)/g, '').trim()}</p>
                </div>
            `;
        }
    });
    html += '</div>';
    
    return html;
}

function formatGeneral(content) {
    // Formato general para contenido no categorizado
    const paragraphs = content.split(/\n\s*\n/).filter(p => p.trim());
    
    let html = '';
    paragraphs.forEach(paragraph => {
        if (paragraph.trim()) {
            html += `<p>${paragraph.trim()}</p>`;
        }
    });
    
    return html || '<p>Contenido no disponible.</p>';
}
