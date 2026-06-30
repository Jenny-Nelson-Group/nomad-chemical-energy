# MIT License

# Copyright (c) 2019

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import re

from baseclasses import PubChemPureSubstanceSectionCustom
from baseclasses.chemical_energy import (
    Purging,
    SubstanceWithConcentration,
    SubstrateProperties,
)
from baseclasses.chemical_energy.cesample import Deposition, Solvent
from baseclasses.helper.utilities import find_sample_by_id
from nomad.datamodel.metainfo.basesections import (
    PureSubstanceComponent,
    PureSubstanceSection,
)
from nomad.units import ureg

from nomad_chemical_energy.schema_packages.ce_nesd_package import (
    CE_NESD_Electrolyte,
    CE_NESD_ReferenceElectrode,
)


def split_catalyst_mxene_materials(material_str):
    # standardize the different separators (-, %, @) to comma
    standardized = re.sub(r'[-%@]', ',', material_str)
    # split by comma or whitespace
    parts = re.split(r'[, ]+', standardized)
    # remove any empty strings
    parts = [p for p in parts if p]
    # keep only strings that contain at least one letter
    materials = [p.replace('Tx', '') for p in parts if re.search(r'[A-Za-z]', p)]
    return materials


def map_sample(entry, data_dict, setup_type, logger):
    entry.name = data_dict.get('active material common name')
    entry.preparation_date = data_dict.get('preparation date')
    entry.origin = data_dict.get('preparing person')

    materials = split_catalyst_mxene_materials(data_dict.get('solutes'))
    if len(materials) > 2 or not materials:
        logger.warn(
            'Could not split given material into catalyst and mxene. Please check your "Solutes" in the metadata excel.'
        )
    material_catalyst, material_mxene = (materials + [None, None])[:2]
    component_catalyst = PureSubstanceComponent(
        pure_substance=PureSubstanceSection(molecular_formula=material_catalyst)
    )
    component_mxene = PureSubstanceComponent(
        pure_substance=PureSubstanceSection(molecular_formula=material_mxene)
    )
    if data_dict.get('solute masses'):
        component_catalyst.mass = (data_dict.get('solute masses', 0) * ureg('mg'),)
    if data_dict.get('Mass Mxene'):
        component_mxene.mass = data_dict.get('Mass Mxene', 0) * ureg('µg')
    components = []
    if material_catalyst:
        components.append(component_catalyst)
    if material_mxene:
        components.append(component_mxene)
    entry.components = components

    entry.drying_temperature = data_dict.get('drying temperature')
    entry.description = data_dict.get('notes (electrode preparation)')

    if setup_type in ['3electrode', 'RDE', 'Half-Cell', 'old_template']:
        entry.substrate = SubstrateProperties(
            substrate_type=data_dict.get('substrate type'),
            substrate_cleaning=data_dict.get('substrate cleaning'),
        )

    if setup_type in ['3electrode', 'RDE', 'old_template']:
        entry.active_area = data_dict.get('working electrode: active area') * ureg(
            'cm^2'
        )
        ink_composition_list = []
        ink_list = [
            solvent.strip()
            for solvent in data_dict.get('solvent volumes', '').split(',')
            if solvent.strip()
        ]
        pattern = re.compile(r'([\d.]+)\s*(ml|mL)\s*(.+)', re.IGNORECASE)
        for solvent in ink_list:
            m = pattern.match(solvent)
            if not m:
                logger.warn(
                    'Could not split given ink composition into Solvent name + volume.'
                    'Please check your "Solvent Volumes" field in the top part of the metadata excel.'
                )
                continue
            volume = float(m.group(1))
            unit = m.group(2).strip()
            solvent_type = m.group(3).strip()
            ink_composition_list.append(
                Solvent(type=solvent_type, volume=volume * ureg(unit))
            )
        deposition_volume = data_dict.get('deposition volume')
        catalyst_loading = data_dict.get('catalyst loading')
        mass = data_dict.get('total mass of hybrid catalyst on electrode after drying')
        deposition_notes = data_dict.get('notes (deposition method)', '')
        entry.deposition = Deposition(
            catalyst_layer_deposition_method=data_dict.get(
                'catalyst layer deposition method'
            ),
            ink_composition=ink_composition_list,
            deposition_volume=deposition_volume * ureg('µl')
            if deposition_volume is not None
            else None,
            catalyst_loading=catalyst_loading * ureg('mg/cm^2')
            if catalyst_loading is not None
            else None,
            binder=data_dict.get('binder'),
            description=(
                f'Total mass of hybrid catalyst on electrode after drying: {mass}mg <br><br>'
                if mass
                else ''
            )
            + deposition_notes,
        )


def get_environment(data_dict):
    entry = CE_NESD_Electrolyte()
    entry.solvent = PubChemPureSubstanceSectionCustom(name='H20', load_data=False)
    entry.substances = [
        SubstanceWithConcentration(
            name=data_dict.get('electrolyte: substance'),
            concentration_mmol_per_l=data_dict.get('electrolyte: concentration'),
            substance=PubChemPureSubstanceSectionCustom(
                name=data_dict.get('electrolyte: substance'), load_data=False
            ),
        )
    ]
    entry.ph_value = data_dict.get('electrolyte: ph')
    entry.purging = Purging(
        time=data_dict.get('electrolyte: purging time'),
        temperature=data_dict.get('electrolyte: purging temperature'),
        gas=PubChemPureSubstanceSectionCustom(
            name=data_dict.get('electrolyte: purging gas'), load_data=False
        ),
    )
    return entry


def get_reference_electrode(data_dict):
    entry = CE_NESD_ReferenceElectrode()
    entry.name = data_dict.get('reference electrode: type')
    entry.standard_potential = data_dict.get(
        'reference electrode: standard potential at 25 °c'
    ) * ureg('V')
    entry.temperature = data_dict.get('reference electrode: temperature')
    return entry


def map_setup(entry, data_dict, setup_type, archive):
    entry.setup = setup_type
    entry.origin = data_dict.get('experimentalist: name')
    if data_dict.get('measurement date'):
        entry.datetime = data_dict.get('measurement date')

    potentiostat = find_sample_by_id(archive, data_dict.get('potentiostat model'))
    entry.equipment = [potentiostat] if potentiostat is not None else None
    entry.description = data_dict.get('general information and notes')

    if setup_type != 'AEM_or_PEM':
        entry.environment = get_environment(data_dict)
    entry.ir_compensation = (
        data_dict.get('ir compensation') / 100
        if data_dict.get('ir compensation') is not None
        else None
    )

    # TODO revisit when reference electrodes in the lab get ids (then link ref and counter electrodes here)
    # entry.reference_electrode_subsection = get_reference_electrode(data_dict)
    # data_dict.get('Counter electrode: Material')
    # data_dict.get('Electrode holder & conductive connection')

    # entry.setup_id = SampleIDCENESD(owner=data_dict.get('Experimentalist: Name'))
